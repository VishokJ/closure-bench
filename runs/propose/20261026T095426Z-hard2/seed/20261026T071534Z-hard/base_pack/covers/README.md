# Functional coverage model (uart)

One file per plan item in ../plan.yaml: `<ID>.sv` holds module `cov_<ID>`
and its own `bind` to the unmodified RTL. Each cover label is its plan ID plus
a name (e.g. `R1_frame_error`); tools/check verifies the plan and these files
stay in sync.
