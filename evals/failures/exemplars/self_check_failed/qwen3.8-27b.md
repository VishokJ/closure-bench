# self_check_failed: qwen/qwen3.8-27b

Rollout `qwen3.8-27b/R20/0` (/Users/vishokj/Developer/cb-probe/outputs/official/qwen/closure-bench--qwen--qwen3.8-27b--null--ec46d01c/traces.jsonl:8), task R20, grade status `runtime_error`. Picked as the median submission length (3284 chars) of 7 rollouts in this category for this model.

Sub-label: `watchdog`

## Evidence

```json
{
 "diagnostic": "Assertion failed in TOP.tb: timeout",
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
   "gold_event": "cycle 155 rx busy_fall 0",
   "index": 2,
   "matched_before": 2,
   "of": 4
  },
  "submission_cycles": [
   6
  ]
 },
 "line": 116,
 "replay": {
  "gold_status": "ok",
  "gold_target_hits": {
   "R20": 1
  },
  "matches_trace": true,
  "status": "runtime_error",
  "target_hits": {
   "R20": 0
  }
 }
}
```

Residual label: **wrong_self_check**: The 3C frame is received and accepted mid-stop-bit (sub `386 3108000 rx hs 3c`), but uart_send_byte keeps driving the full stop bit before calling wait_tvalid_rise, so tvalid has already risen and fallen. That wait hangs, the A5 frame is never sent (no counterpart to gold `155 ... rx hs a5`), and the 10ms timeout $fatal fires.

## Gold excerpt (formal witness)

```systemverilog
// gold_source: formal
// closure_core.formal.cover_witness: depth 157, input_changes 14, bound 300, witness 4f445d7512ef6b54
// Formal witness for R20_rx_single_cycle_stall_accept (closure_core/formal.py): the shortest legal input
// trace Yosys/SymbiYosys found (157 cycles), replayed on the uart_rx ports.
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
    repeat (30) @(negedge clk);
    rxd = 1'd0;
    repeat (18) @(negedge clk);
    rxd = 1'd1;
    @(negedge clk);
    rxd = 1'd0;
    repeat (5) @(negedge clk);
    rxd = 1'd1;
    repeat (7) @(negedge clk);
    rxd = 1'd0;
    repeat (9) @(negedge clk);
    rxd = 1'd1; m_axis_tready = 1'd0;
    repeat (11) @(negedge clk);
    rxd = 1'd0;
    repeat (13) @(negedge clk);
    rxd = 1'd1;
    repeat (13) @(negedge clk);
    rxd = 1'd0;
    repeat (8) @(negedge clk);
    rxd = 1'd1;
    repeat (12) @(negedge clk);
    m_axis_tready = 1'd1;
    repeat (3) @(negedge clk);
    $finish;
  end
endmodule
```

## Gold event log

```
1 15000 rx prescale 1
3 35000 rx busy_rise 0
78 785000 rx hs 3c
155 1555000 rx busy_fall 0
155 1555000 rx hs a5
```

## Submission event log

```
1 28000 rx prescale 5
6 68000 rx busy_rise 0
386 3108000 rx busy_fall 0
386 3108000 rx hs 3c
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
  "gold_event": "cycle 155 rx busy_fall 0",
  "index": 2,
  "matched_before": 2,
  "of": 4
 },
 "submission_cycles": [
  6
 ]
}
```

## Submission excerpt

```systemverilog
`timescale 1ns / 1ps

module tb;

  localparam int          CLK_PERIOD = 8;
  localparam logic [15:0] PRESCALE   = 16'd5;

  logic        clk = 1'b0;
  logic        rst = 1'b1;
  logic        rxd = 1'b1;
  logic        m_axis_tready = 1'b1;
  logic [15:0] prescale = PRESCALE;
  wire  [7:0]  m_axis_tdata;
  wire         m_axis_tvalid;
  wire         busy;
  wire         overrun_error;
  wire         frame_error;

  always #(CLK_PERIOD / 2) clk = ~clk;

  // Receiver under test, default DATA_WIDTH = 8.
  uart_rx dut (
    .clk(clk), .rst(rst),
    .m_axis_tdata(m_axis_tdata), .m_axis_tvalid(m_axis_tvalid),
    .m_axis_tready(m_axis_tready),
    .rxd(rxd),
    .busy(busy), .overrun_error(overrun_error), .frame_error(frame_error),
    .prescale(prescale)
  );

  // Reactive back-pressure generator.
  // Every time m_axis_tvalid rises, m_axis_tready is held low for exactly one
  // rising clock edge and then raised, so the word is accepted after exactly
  // one stall cycle (this is what R20 requires for the 0xA5 word).
  logic tv_n   = 1'b0;
  logic stall1 = 1'b0;

  always @(negedge clk) begin
    if (rst) begin
      m_axis_tready <= 1'b1;
      tv_n          <= 1'b0;
      stall1        <= 1'b0;
    end else begin
      if (stall1) begin
        m_axis_tready <= 1'b1;   // second edge of the stall window: accept
        stall1        <= 1'b0;
      end else if (m_axis_tvalid && !tv_n) begin
        m_axis_tready <= 1'b0;   // first edge where tvalid is high: stall
        stall1        <= 1'b1;
      end else begin
        m_axis_tready <= 1'b1;   // default: ready
      end
      tv_n <= m_axis_tvalid;
    end
  end

  task automatic wait_clks(input int n);
    repeat (n) @(negedge clk);
  endtask

  task automatic do_reset();
    rst = 1'b1; wait_clks(3);
    rst = 1'b0; wait_clks(3);
  endtask

  task automatic wait_tvalid_rise();
    do begin
      @(negedge clk);
    end while (!m_axis_tvalid);
  endtask

  task automatic wait_tvalid_fall();
    do begin
      @(negedge clk);
    end while (m_axis_tvalid);
  endtask

  // Well-formed 8N1 frame on rxd, LSB first, each bit prescale*8 clocks.
  task automatic uart_send_byte(input logic [7:0] b);
    int bit_clks = int'(prescale) * 8;
```
