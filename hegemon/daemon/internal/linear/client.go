package linear

import (
	"bytes"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"time"
)

const endpoint = "https://api.linear.app/graphql"

// Client is a Linear GraphQL API client.
type Client struct {
	apiKey string
	teamID string
	http   *http.Client
	// Cached workflow state IDs (resolved once at startup).
	stateIDs map[string]string // state name → id
}

// Issue represents a Linear issue with fields relevant to dispatch.
type Issue struct {
	ID          string
	Identifier  string
	Title       string
	Description string
	Estimate    int
	Priority    int
	Labels      []string
	StateID     string
	StateName   string
	StateType   string
}

// Cycle represents a Linear cycle (sprint).
type Cycle struct {
	ID       string
	Name     string
	StartsAt time.Time
	EndsAt   time.Time
}

// New creates a Linear API client.
func New(apiKey, teamID string) *Client {
	return &Client{
		apiKey:   apiKey,
		teamID:   teamID,
		http:     &http.Client{Timeout: 30 * time.Second},
		stateIDs: make(map[string]string),
	}
}

// Init resolves and caches workflow state IDs for the team.
func (c *Client) Init() error {
	states, err := c.getWorkflowStates()
	if err != nil {
		return fmt.Errorf("init workflow states: %w", err)
	}
	for _, s := range states {
		c.stateIDs[s.Name] = s.ID
		// Also index by type for fallback lookup.
		c.stateIDs["type:"+s.Type] = s.ID
	}
	return nil
}

type workflowState struct {
	ID   string `json:"id"`
	Name string `json:"name"`
	Type string `json:"type"`
}

func (c *Client) getWorkflowStates() ([]workflowState, error) {
	query := `query($teamId: ID!) {
		workflowStates(filter: { team: { id: { eq: $teamId } } }) {
			nodes { id name type }
		}
	}`
	var resp struct {
		Data struct {
			WorkflowStates struct {
				Nodes []workflowState `json:"nodes"`
			} `json:"workflowStates"`
		} `json:"data"`
	}
	if err := c.gql(query, map[string]interface{}{"teamId": c.teamID}, &resp); err != nil {
		return nil, err
	}
	return resp.Data.WorkflowStates.Nodes, nil
}

// GetActiveCycle returns the current active cycle for the team.
func (c *Client) GetActiveCycle() (*Cycle, error) {
	query := `query($teamId: String!) {
		team(id: $teamId) {
			activeCycle {
				id name startsAt endsAt
			}
		}
	}`
	var resp struct {
		Data struct {
			Team struct {
				ActiveCycle *struct {
					ID       string `json:"id"`
					Name     string `json:"name"`
					StartsAt string `json:"startsAt"`
					EndsAt   string `json:"endsAt"`
				} `json:"activeCycle"`
			} `json:"team"`
		} `json:"data"`
	}
	if err := c.gql(query, map[string]interface{}{"teamId": c.teamID}, &resp); err != nil {
		return nil, err
	}
	ac := resp.Data.Team.ActiveCycle
	if ac == nil {
		return nil, nil
	}
	startsAt, _ := time.Parse(time.RFC3339, ac.StartsAt)
	endsAt, _ := time.Parse(time.RFC3339, ac.EndsAt)
	return &Cycle{ID: ac.ID, Name: ac.Name, StartsAt: startsAt, EndsAt: endsAt}, nil
}

// GetCycleIssues returns issues in a cycle filtered by state type (e.g., "unstarted").
func (c *Client) GetCycleIssues(cycleID, stateType string) ([]Issue, error) {
	query := `query($cycleId: ID!, $stateType: String!) {
		issues(filter: {
			cycle: { id: { eq: $cycleId } }
			state: { type: { eq: $stateType } }
		}, first: 100) {
			nodes {
				id identifier title description
				estimate priority
				labels { nodes { name } }
				state { id name type }
			}
		}
	}`
	var resp struct {
		Data struct {
			Issues struct {
				Nodes []struct {
					ID          string `json:"id"`
					Identifier  string `json:"identifier"`
					Title       string `json:"title"`
					Description string `json:"description"`
					Estimate    int    `json:"estimate"`
					Priority    int    `json:"priority"`
					Labels      struct {
						Nodes []struct {
							Name string `json:"name"`
						} `json:"nodes"`
					} `json:"labels"`
					State struct {
						ID   string `json:"id"`
						Name string `json:"name"`
						Type string `json:"type"`
					} `json:"state"`
				} `json:"nodes"`
			} `json:"issues"`
		} `json:"data"`
	}
	if err := c.gql(query, map[string]interface{}{"cycleId": cycleID, "stateType": stateType}, &resp); err != nil {
		return nil, err
	}

	var issues []Issue
	for _, n := range resp.Data.Issues.Nodes {
		var labels []string
		for _, l := range n.Labels.Nodes {
			labels = append(labels, l.Name)
		}
		issues = append(issues, Issue{
			ID:          n.ID,
			Identifier:  n.Identifier,
			Title:       n.Title,
			Description: n.Description,
			Estimate:    n.Estimate,
			Priority:    n.Priority,
			Labels:      labels,
			StateID:     n.State.ID,
			StateName:   n.State.Name,
			StateType:   n.State.Type,
		})
	}
	return issues, nil
}

// UpdateIssueState moves an issue to a new workflow state.
func (c *Client) UpdateIssueState(issueID, stateName string) error {
	stateID, ok := c.stateIDs[stateName]
	if !ok {
		return fmt.Errorf("unknown state %q (cached states: %v)", stateName, c.stateIDs)
	}
	query := `mutation($id: String!, $stateId: String!) {
		issueUpdate(id: $id, input: { stateId: $stateId }) {
			success
		}
	}`
	var resp struct {
		Data struct {
			IssueUpdate struct {
				Success bool `json:"success"`
			} `json:"issueUpdate"`
		} `json:"data"`
	}
	if err := c.gql(query, map[string]interface{}{"id": issueID, "stateId": stateID}, &resp); err != nil {
		return err
	}
	if !resp.Data.IssueUpdate.Success {
		return fmt.Errorf("issue update failed for %s → %s", issueID, stateName)
	}
	return nil
}

// CreateComment posts a markdown comment on an issue.
func (c *Client) CreateComment(issueID, body string) error {
	query := `mutation($issueId: String!, $body: String!) {
		commentCreate(input: { issueId: $issueId, body: $body }) {
			success
		}
	}`
	var resp struct {
		Data struct {
			CommentCreate struct {
				Success bool `json:"success"`
			} `json:"commentCreate"`
		} `json:"data"`
	}
	return c.gql(query, map[string]interface{}{"issueId": issueID, "body": body}, &resp)
}

// gql executes a GraphQL query against the Linear API.
func (c *Client) gql(query string, variables map[string]interface{}, result interface{}) error {
	body, err := json.Marshal(map[string]interface{}{
		"query":     query,
		"variables": variables,
	})
	if err != nil {
		return fmt.Errorf("marshal query: %w", err)
	}

	req, err := http.NewRequest("POST", endpoint, bytes.NewReader(body))
	if err != nil {
		return fmt.Errorf("create request: %w", err)
	}
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("Authorization", c.apiKey)

	resp, err := c.http.Do(req)
	if err != nil {
		return fmt.Errorf("linear API: %w", err)
	}
	defer resp.Body.Close()

	respBody, err := io.ReadAll(resp.Body)
	if err != nil {
		return fmt.Errorf("read response: %w", err)
	}

	if resp.StatusCode != 200 {
		return fmt.Errorf("linear API %d: %s", resp.StatusCode, string(respBody))
	}

	// Check for GraphQL errors.
	var gqlResp struct {
		Errors []struct {
			Message string `json:"message"`
		} `json:"errors"`
	}
	if err := json.Unmarshal(respBody, &gqlResp); err == nil && len(gqlResp.Errors) > 0 {
		return fmt.Errorf("graphql error: %s", gqlResp.Errors[0].Message)
	}

	return json.Unmarshal(respBody, result)
}
