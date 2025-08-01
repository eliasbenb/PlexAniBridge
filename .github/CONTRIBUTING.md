# Contributing

Contributions to PlexAniBridge are always appreciated! Please follow the guidelines below to help us maintain a high-quality codebase.

## Development

This guide is for developers who want to contribute to the backend of the PlexAniBridge project. It assumes you'll be using Visual Studio Code with Dev Containers (requires Docker). Of course, you are free to use any IDE you prefer, but the VS Code IDE and Devcontainer settings are already pre-configured with linting and dependency management for you.

If you decide to use a different IDE, you will need to set up the environment manually and infer the project's dependencies yourself. Take a look at [`.devcontainer/devcontainer.json`](/.devcontainer/devcontainer.json) for an idea of what's required.

### Tools required

- [Visual Studio Code](https://code.visualstudio.com/) with the [Dev Containers](https://code.visualstudio.com/docs/remote/containers) extension
- [Docker](https://www.docker.com/)

### Getting started

1. Fork PlexAniBridge.
2. Clone the repository into your development machine ([_info_](https://docs.github.com/en/get-started/quickstart/fork-a-repo)).
3. Open the project in Visual Studio Code, it will prompt you to reopen in a dev container, do so.
4. If you didn't recieve a prompt, you can also open the command palette (Ctrl+Shift+P) and select "Reopen in Container".
5. The dev container will build and setup all required packages and dependencies.
6. Once the dev container is ready, you can start activate the Python virtual environment with `source .venv/bin/activate`.

## Documentation

If you are only making changes to the documentation, you can opt to clone the repository and edit the documentation files in your preferred text editor or directly in the GitHub web UI. The documentation is located in the `docs/` directory.

1. Fork PlexAniBridge.
2. Clone the repository into your development machine ([_info_](https://docs.github.com/en/get-started/quickstart/fork-a-repo)) or edit directly in the GitHub web UI.
3. Make your changes to the documentation files in the `docs/` directory.

## Contributing Code

- Follow the coding standard. We use [ruff](https://docs.astral.sh/ruff/) for static code analysis and [pytest](https://docs.pytest.org/en/stable/) for unit testing.
  - Run `ruff check` to ensure your code adheres to the project's linting rules.
  - Run `pytest` to ensure all tests pass.
- If your change adds or modifies functionality, write tests to verify its behavior in the `tests/` directory.
- Update or add documentation in the `docs/` directory if it affects usage or APIs.
- Make sure any complex or non-obvious code is explained with comments. This helps maintain readability and ease of review.

## Pull Requesting

- Make pull requests to the default branch.
- Please ensure your pull request has a clear title and description.
- Fill out the pull request template in its entirety, it helps us understand what your changes are and why they are needed.
- Each PR should come from its own [feature branch](http://martinfowler.com/bliki/FeatureBranch.html) not develop in your fork, it should have a meaningful branch name (what is being added/fixed).
  - new-feature (Good)
  - fix-bug (Good)
  - patch (Bad)
  - develop (Bad)
- Each PR should solve one issue or add one feature (or a group of meaningfully connected issues/features), if you have multiple, please create a separate PR for each.
- Check for existing pull requests at https://github.com/eliasbenb/PlexAniBridge/pulls to avoid duplicates.
