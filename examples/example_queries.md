# Example Queries

Try these after starting the CLI with `uv run mini-aec-agent`.

For a single non-interactive question, run:

```bash
uv run mini-aec-agent --question "Is Door-01 compliant?" --trace
```

## Single-item checks

- `Is Door-01 compliant?`
- `Is Door-02 compliant?`
- `Check Room-101 for compliance.`
- `Does Room-102 meet the demonstration rules?`

## Multi-step checks

- `Which doors in the building fail compliance?`
- `Which offices fail compliance?`
- `Check all doors and tell me which ones pass.`

## Missing-item handling

- `Is Door-99 compliant?`

The current dataset and rules are deliberately small so the tool-use behavior can be inspected and evaluated easily.
