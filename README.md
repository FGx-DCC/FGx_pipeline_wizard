# Config/Run wizard

This is a collection of scripts (with entry point `main.py`) that will generate
a wrapper script (run.sh) with an accompanying configuration file. These files
are generated from `toml` files that describe the steps of a pipeline and user
input. The idea is this:

- A user can select from a set of pipelines (or create their own)
- The user can then remove branches of the pipeline they don't need (perhaps
  they don't need to run fastqc on their files as this is already done)
- The user can also choose to start from any step in the pipeline (in case of a
  previous run failing perhaps) and also end prematurely (if later steps aren't
  required for their experiment)
- The user is then told which external files are required (and optional
  downloads can occur if files are missing)
- The user can then input any variables that scripts need (which is written to
  a configuration file, which set environment variables for shell scripts to
  use)
- A `run.sh` and configuration file is generated, which can be ran using bash.

A user is capable of changing the `run.sh` or configuration file themselves
manually, but they may not be comfortable with this. For this reason, the user
may want to rerun this tool to update these files.

## toml format

Pipelines are written in [toml](https://toml.io/en/) like so:

```toml
name = "Test Pipeline"
description = "A test pipeline with read, clean and write steps"

[parameters]
out_directory = "/path/to/output/directory/"
keep_temporary = false

[steps.read]
path = "read.sh"
description = "Read the data from a file and convert to pandas"

[steps.clean]
path = "clean.sh"
description = "Use interpolation to remove missingness"
requires = ["https://www.example.com/reference"]
after = ["read"]
[steps.clean.parameters]
max_distance = 5
tool_version = ["v1", "v2"]

[steps.write]
path = "write.sh"
after = ["clean"]
[steps.write.parameters]
out_path = "/desired/path/to/output/"

[steps.report]
dag = "report.toml"
after = ["write"]
```

Key:

- Sections are denoted by `[steps.step_name]`
- path -> The path (relative to some scripts directory) the script lies
- description -> The description of the pipeline (top) or step
- after -> What scripts need to complete successfully for this one to run (a
  prerequisite)
- requires -> An external file that is required (for example, a genome fasta)
- dag -> A path to another toml to embed into this one (allows for more
  flexibility and modularity)
- Parameters -> Denoted in `key = value` pairs under section header
  `[steps.step_name.parameters]`
  - The value given is considered a default. The user will be asked if they
    wish to override this.
  - If a list is given for value (`[option_1, option_2]`), the user will be
    given this list of options to choose from (rather than trying to guess at a
    different value)
- `[parameters]` -> This is a section for defining parameters that are used in
  multiple scripts. It is also given as key value pairs like above.
  - It is not recommended to use this for one off cases as users can remove
    branches they don't need. If a parameter is only used in a single script
    (and that script is removed from the pipeline), it should go under that
    particular script (not the global parameters), else the user would need to
    set a value that is never used.
