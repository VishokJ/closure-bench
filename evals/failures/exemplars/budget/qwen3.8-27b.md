# budget: qwen/qwen3.8-27b

Rollout `qwen3.8-27b/T6/7` (/Users/vishokj/Developer/cb-probe/outputs/official/qwen/closure-bench--qwen--qwen3.8-27b--null--ec46d01c/traces.jsonl:139), task T6, grade status `compile_error`. Picked as the median submission length (0 chars) of 14 rollouts in this category for this model.

Sub-label: `max_tokens`

## Evidence

```json
{
 "finish_reason": "length",
 "max_tokens": 65536,
 "output_tokens": 65536,
 "stop_condition": "agent_completed"
}
```

## Gold excerpt (formal witness)

```systemverilog
// gold_source: formal
// closure_core.formal.cover_witness: depth 157, input_changes 5, bound 300, witness bbd350243ce5d16c
// Formal witness for T6_tvalid_rise_on_frame_end (closure_core/formal.py): the shortest legal input
// trace Yosys/SymbiYosys found (157 cycles), replayed on the uart_tx ports.
// A gold candidate, never shown to an agent; Verilator decides whether it hits.
`timescale 1ns / 1ps

module tb;
  logic clk = 1'b0;
  always #5 clk = ~clk;
  logic rst = 1'd1;
  logic [7:0] s_axis_tdata = 8'd195;
  logic s_axis_tvalid = 1'd0;
  logic [15:0] prescale = 16'd1;
  wire  s_axis_tready;
  wire  txd;
  wire  busy;

  uart_tx dut (.clk(clk), .rst(rst), .s_axis_tdata(s_axis_tdata), .s_axis_tvalid(s_axis_tvalid), .prescale(prescale), .s_axis_tready(s_axis_tready), .txd(txd), .busy(busy));

  initial begin
    @(negedge clk);
    rst = 1'd0; s_axis_tvalid = 1'd1;
    repeat (2) @(negedge clk);
    s_axis_tvalid = 1'd0;
    repeat (37) @(negedge clk);
    s_axis_tdata = 8'd60;
    repeat (42) @(negedge clk);
    s_axis_tvalid = 1'd1;
    repeat (76) @(negedge clk);
    $finish;
  end
endmodule
```

Event logs and divergence: not replayed (only miss, self_check_failed and never_finishes are).

## Submission excerpt

```systemverilog
(empty submission)
```
