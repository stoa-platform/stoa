package adapters

import "encoding/json"

// wmAPI represents an API from webMethods API Gateway.
type wmAPI struct {
	ID             string `json:"id"`
	APIName        string `json:"apiName"`
	APIVersion     string `json:"apiVersion"`
	APIDescription string `json:"apiDescription"`
	IsActive       bool   `json:"isActive"`
	Type           string `json:"type"`
}

// wmAPIWrapper handles the nested response shape: {"api": {...}, "responseStatus": "SUCCESS"}
type wmAPIWrapper struct {
	API            wmAPI  `json:"api"`
	ResponseStatus string `json:"responseStatus"`
}

type wmAPIsResponse struct {
	APIResponse []json.RawMessage `json:"apiResponse"`
}

// wmPolicyAction represents a policy action from webMethods.
type wmPolicyAction struct {
	ID          string `json:"id"`
	TemplateKey string `json:"templateKey"`
	PolicyName  string `json:"policyActionName"`
}

// wmAlias represents an alias from webMethods API Gateway.
type wmAlias struct {
	ID   string `json:"id"`
	Name string `json:"name"`
	Type string `json:"type"`
}

type wmAliasListResponse struct {
	Alias []wmAlias `json:"alias"`
}

// wmStrategy represents a strategy from webMethods API Gateway.
type wmStrategy struct {
	ID   string `json:"id"`
	Name string `json:"name"`
}

type wmStrategyListResponse struct {
	Strategies []wmStrategy `json:"strategy"`
}

// wmTransactionalEvent represents a raw transactional event from webMethods.
type wmTransactionalEvent struct {
	EventTimestamp string `json:"eventTimestamp"` // epoch millis as string
	APIID          string `json:"apiId"`
	APIName        string `json:"apiName"`
	OperationName  string `json:"operationName"`
	HTTPMethod     string `json:"httpMethod"`
	ResourcePath   string `json:"resourcePath"`
	Status         int    `json:"status"`
	TotalTime      int64  `json:"totalTime"` // milliseconds
	TenantID       string `json:"tenantId"`
}
