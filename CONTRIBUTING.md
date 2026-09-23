# Contributing to JevMatch

Thanks for helping make resume matching more transparent and responsible.

## Development

1. Fork the repository and create a focused branch.
2. Install [uv](https://docs.astral.sh/uv/) and Node.js 22 or newer.
3. Run `make install`, then `make test` and `make lint` before opening a pull request.
4. Add tests for behavioral changes. Never add real resumes, API keys, or personally identifying
   candidate data to fixtures, logs, issues, or commits.

Pull requests should explain the problem, the chosen behavior, and any effect on scoring or review
thresholds. Changes to scoring must remain deterministic and include regression tests. Changes to
model questions should include an explanation of how they were evaluated.

By participating, you agree to follow the [Code of Conduct](CODE_OF_CONDUCT.md).
