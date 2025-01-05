name: Bug Report
description: 'Make sure to read through all instructions in the bug report template before submitting.'
labels: ['bug']
body:

- type: checkboxes
  attributes:
  label: Is there an existing issue for this?
  description: Please search to see if an open or closed issue already exists for the bug you encountered. If a bug exists and it is closed as complete it may not yet be in a stable release.
  options:
  - label: I have searched the existing open and closed issues
    required: true
- type: textarea
  attributes:
  label: Current Behavior
  description: A concise description of what you're experiencing.
  validations:
  required: true
- type: textarea
  attributes:
  label: Expected Behavior
  description: A concise description of what you expected to happen.
  validations:
  required: true
- type: textarea
  attributes:
  label: Steps To Reproduce
  description: Steps to reproduce the behavior.
  placeholder: | 1. In this environment... 2. With this config... 3. Run '...' 4. See error...
  validations:
  required: false
- type: textarea
  attributes:
  label: Environment
  description: |
  examples: - **OS**: Ubuntu 22.04 - **PlexAniBridge**: PlexAniBridge 0.2.2 - **Docker Install**: Yes - **Database**: Sqlite 3.41.1
  value: | - OS: - PlexAniBridge: - Docker Install: - Database:
  render: markdown
  validations:
  required: true
- type: dropdown
  attributes:
  label: What branch are you running?
  options: - Main (`:latest` or `:main` for Docker) - Develop (`:develop` for Docker) - Other (This issue will be closed)
  validations:
  required: true
- type: textarea
  attributes:
  label: Debug Logs?
  description: |
  Debug Logs
  **_Generally speaking, all bug reports must have debug logs provided._**
  **\_ Info Logs are not debug logs. If the logs do not say `DEBUG` and are not from a file like `*.DEBUG.log` they are not debug logs.\_**
  validations:
  required: true
- type: textarea
  attributes:
  label: Anything else?
  description: |
  Links? Screenshots? References? Anything that will give us more context about the issue you are encountering!
  Tip: You can attach images or log files by clicking this area to highlight it and then dragging files in.
  validations:
  required: false
