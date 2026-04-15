Debug a page in a real browser via Playwright MCP. Captures console errors, network failures, and takes a screenshot.

**Argument**: URL to debug (e.g., `https://console.gostoa.dev`, `http://localhost:5173`)

## Steps

1. **Navigate** to `$ARGUMENTS` using `mcp__playwright__browser_navigate`
   - If no URL provided, ask the user

2. **Wait** 3 seconds for the page to load fully using `mcp__playwright__browser_wait_for`
   - Wait for `networkidle` state if possible, otherwise use a short timeout

3. **Capture console messages** using `mcp__playwright__browser_console_messages`
   - Categorize by type: `error`, `warning`, `log`, `info`
   - Highlight errors and warnings prominently

4. **Capture network failures** using `mcp__playwright__browser_network_requests`
   - Filter for failed requests (status >= 400 or connection errors)
   - Show URL, status code, and error text

5. **Take a snapshot** (accessibility tree) using `mcp__playwright__browser_snapshot`
   - Use this to understand the current DOM state

6. **Take a screenshot** using `mcp__playwright__browser_take_screenshot`
   - Full page screenshot for visual context

7. **Report** findings in a compact table:

```
## Browser Debug Report: <URL>

### Console Errors (N)
| Type | Message | Source |
|------|---------|--------|

### Network Failures (N)
| URL | Status | Error |
|-----|--------|-------|

### Page State
- Title: ...
- Load time: ...
- Screenshot: (inline)

### Verdict
- Clean / Has errors / Has warnings
```

## Tips

- Run multiple times to catch intermittent errors
- Use after a deploy to verify no JS errors on key pages
- Combine with `browser_evaluate` to run custom JS assertions:
  ```
  mcp__playwright__browser_evaluate({ expression: "document.querySelectorAll('.error').length" })
  ```
- To debug auth flows, navigate to the login page first, then use `browser_fill_form` + `browser_click`
