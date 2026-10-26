# miss: openai/gpt-6-sol

Rollout `gpt-6-sol/R26/6` (/Users/vishokj/Developer/cb-probe/outputs/official/gpt-6-sol/closure-bench--openai--gpt-6-sol--null--2fc9e854/traces.jsonl:77), task R26, grade status `ok`. Picked as the median submission length (1512 chars) of 7 rollouts in this category for this model.

Sub-label: `None`

## Evidence

```json
{
 "first_divergence": {
  "gold_event": "cycle 3 rx busy_rise 0",
  "index": 0,
  "prescale": {
   "gold": [
    1
   ],
   "submission": [
    5
   ]
  },
  "reason": "at a different cycle",
  "sequence": {
   "gold_event": "cycle 230 rx overrun_error 1",
   "index": 2,
   "matched_before": 2,
   "of": 4
  },
  "submission_cycles": [
   8,
   488,
   1288
  ]
 },
 "other_items_hit": [
  "R1",
  "R19"
 ],
 "replay": {
  "gold_status": "ok",
  "gold_target_hits": {
   "R26": 1
  },
  "matches_trace": true,
  "status": "ok",
  "target_hits": {
   "R26": 0
  }
 },
 "target_hits": {
  "R26": 0
 }
}
```

Residual label: **timing_arithmetic**: The bad stop bit is held low for a full 40-cycle bit after uart_rx samples it at mid-bit (sub `867 ... rx frame_error 1`), so the receiver immediately starts a phantom frame (no busy_fall), whose stop lands inside the A5 frame (sub `1247 ... rx frame_error 1`); A5 is mis-sampled and gold's `230 ... rx overrun_error 1` never occurs.

## Gold excerpt (formal witness)

```systemverilog
// gold_source: formal
// closure_core.formal.cover_witness: depth 232, input_changes 13, bound 300, witness 69cd85593ae6ce67
// Formal witness for R26_frame_error_then_overrun (closure_core/formal.py): the shortest legal input
// trace Yosys/SymbiYosys found (232 cycles), replayed on the uart_rx ports.
// A gold candidate, never shown to an agent; Verilator decides whether it hits.
`timescale 1ns / 1ps

module tb;
  logic clk = 1'b0;
  always #5 clk = ~clk;
  logic rst = 1'd1;
  logic rxd = 1'd0;
  logic m_axis_tready = 1'd1;
  logic [15:0] prescale = 16'd1;
  wire  [7:0] m_axis_tdata;
  wire  m_axis_tvalid;
  wire  busy;
  wire  overrun_error;
  wire  frame_error;

  uart_rx dut (.clk(clk), .rst(rst), .rxd(rxd), .m_axis_tready(m_axis_tready), .prescale(prescale), .m_axis_tdata(m_axis_tdata), .m_axis_tvalid(m_axis_tvalid), .busy(busy), .overrun_error(overrun_error), .frame_error(frame_error));

  initial begin
    @(negedge clk);
    rst = 1'd0;
    repeat (27) @(negedge clk);
    rxd = 1'd1;
    repeat (32) @(negedge clk);
    rxd = 1'd0;
    repeat (15) @(negedge clk);
    rxd = 1'd1; m_axis_tready = 1'd0;
    repeat (2) @(negedge clk);
    rxd = 1'd0;
    repeat (81) @(negedge clk);
    rxd = 1'd1;
    repeat (14) @(negedge clk);
    rxd = 1'd0;
    repeat (3) @(negedge clk);
    rxd = 1'd1;
    repeat (10) @(negedge clk);
    rxd = 1'd0;
    repeat (14) @(negedge clk);
    rxd = 1'd1;
    repeat (12) @(negedge clk);
    rxd = 1'd0;
    repeat (9) @(negedge clk);
    rxd = 1'd1;
    repeat (13) @(negedge clk);
    $finish;
  end
endmodule
```

## Gold event log

```
1 15000 rx prescale 1
3 35000 rx busy_rise 0
154 1545000 rx frame_error 1
230 2305000 rx overrun_error 1
231 2315000 rx busy_fall 0
```

## Submission event log

```
1 44000 rx prescale 5
8 100000 rx busy_rise 0
388 3140000 rx busy_fall 0
488 3940000 rx busy_rise 0
867 6972000 rx frame_error 1
1247 10012000 rx frame_error 1
1248 10020000 rx busy_fall 0
1288 10340000 rx busy_rise 0
```

## First divergence

```json
{
 "gold_event": "cycle 3 rx busy_rise 0",
 "index": 0,
 "prescale": {
  "gold": [
   1
  ],
  "submission": [
   5
  ]
 },
 "reason": "at a different cycle",
 "sequence": {
  "gold_event": "cycle 230 rx overrun_error 1",
  "index": 2,
  "matched_before": 2,
  "of": 4
 },
 "submission_cycles": [
  8,
  488,
  1288
 ]
}
```

## Submission excerpt

```systemverilog
`timescale 1ns / 1ps

module tb;
  localparam int BIT_CYCLES = 40;  // 8 clocks per prescale unit

  logic clk = 1'b0;
  logic rst = 1'b1;
  logic rxd = 1'b1;
  logic m_axis_tready = 1'b0;
  logic [15:0] prescale = 16'd5;

  wire [7:0] m_axis_tdata;
  wire m_axis_tvalid;
  wire busy;
  wire overrun_error;
  wire frame_error;

  always #4 clk = ~clk;

  uart_rx dut (
    .clk(clk),
    .rst(rst),
    .m_axis_tdata(m_axis_tdata),
    .m_axis_tvalid(m_axis_tvalid),
    .m_axis_tready(m_axis_tready),
    .rxd(rxd),
    .busy(busy),
    .overrun_error(overrun_error),
    .frame_error(frame_error),
    .prescale(prescale)
  );

  task automatic wait_clks(input int n);
    repeat (n) @(negedge clk);
  endtask

  task automatic send_frame(input logic [7:0] data, input logic stop_bit);
    rxd = 1'b0;
    wait_clks(BIT_CYCLES);
    for (int i = 0; i < 8; i++) begin
      rxd = data[i];
      wait_clks(BIT_CYCLES);
    end
    rxd = stop_bit;
    wait_clks(BIT_CYCLES);
  endtask

  initial begin
    wait_clks(5);
    rst = 1'b0;
    wait_clks(5);

    // Leave 3C pending under back-pressure.
    send_frame(8'h3C, 1'b1);
    rxd = 1'b1;
    wait_clks(2 * BIT_CYCLES);

    // A low stop bit produces frame_error without consuming the pending word.
    send_frame(8'h55, 1'b0);
    rxd = 1'b1;
    wait_clks(3 * BIT_CYCLES);

    // This good frame replaces the unread 3C and produces overrun_error.
    send_frame(8'hA5, 1'b1);
    rxd = 1'b1;
    wait_clks(2 * BIT_CYCLES);

    $finish;
  end
endmodule
```
