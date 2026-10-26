# miss: qwen/qwen3.8-27b

Rollout `qwen3.8-27b/R29/2` (/Users/vishokj/Developer/cb-probe/outputs/official/qwen/closure-bench--qwen--qwen3.8-27b--null--ec46d01c/traces.jsonl:76), task R29, grade status `ok`. Picked as the median submission length (2620 chars) of 13 rollouts in this category for this model.

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
    1,
    1
   ]
  },
  "reason": "at a different cycle",
  "sequence": {
   "gold_event": "cycle 154 rx frame_error 1",
   "index": 2,
   "matched_before": 2,
   "of": 3
  },
  "submission_cycles": [
   5,
   86
  ]
 },
 "other_items_hit": [
  "R1",
  "R19"
 ],
 "replay": {
  "gold_status": "ok",
  "gold_target_hits": {
   "R29": 1
  },
  "matches_trace": true,
  "status": "ok",
  "target_hits": {
   "R29": 0
  }
 },
 "target_hits": {
  "R29": 0
 }
}
```

Residual label: **timing_arithmetic**: The scenario has the right shape (3c held, then a bad-stop frame), but tready is raised by cycle counting that assumes the frame_error strobe comes at the end of the stop bit; the strobe actually fires earlier (sub `161 ... rx frame_error 1`), so the handshake lands two cycles late (sub `163 ... rx hs 3c`) instead of on the same clock (gold `154 ... rx hs 3c` / `154 ... rx frame_error 1`).

## Gold excerpt (formal witness)

```systemverilog
// gold_source: formal
// closure_core.formal.cover_witness: depth 157, input_changes 6, bound 300, witness a11acad5d6fbec67
// Formal witness for R29_accept_during_frame_error (closure_core/formal.py): the shortest legal input
// trace Yosys/SymbiYosys found (157 cycles), replayed on the uart_rx ports.
// A gold candidate, never shown to an agent; Verilator decides whether it hits.
`timescale 1ns / 1ps

module tb;
  logic clk = 1'b0;
  always #5 clk = ~clk;
  logic rst = 1'd1;
  logic rxd = 1'd0;
  logic m_axis_tready = 1'd0;
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
    repeat (26) @(negedge clk);
    rxd = 1'd1;
    repeat (26) @(negedge clk);
    rxd = 1'd0;
    repeat (17) @(negedge clk);
    rxd = 1'd1;
    repeat (7) @(negedge clk);
    rxd = 1'd0;
    repeat (77) @(negedge clk);
    m_axis_tready = 1'd1;
    repeat (4) @(negedge clk);
    $finish;
  end
endmodule
```

## Gold event log

```
1 15000 rx prescale 1
3 35000 rx busy_rise 0
154 1545000 rx hs 3c
154 1545000 rx frame_error 1
```

## Submission event log

```
1 45000 tx prescale 1
1 45000 rx prescale 1
5 85000 rx busy_rise 0
81 845000 rx busy_fall 0
86 895000 rx busy_rise 0
161 1645000 rx frame_error 1
163 1665000 rx hs 3c
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
   1,
   1
  ]
 },
 "reason": "at a different cycle",
 "sequence": {
  "gold_event": "cycle 154 rx frame_error 1",
  "index": 2,
  "matched_before": 2,
  "of": 3
 },
 "submission_cycles": [
  5,
  86
 ]
}
```

## Submission excerpt

```systemverilog
`timescale 1ns / 1ps

module tb;
  localparam int CLK_PERIOD = 10;
  localparam logic [15:0] PRESCALE = 16'd1;

  logic clk = 0;
  logic rst = 0;
  logic [7:0] m_axis_tdata;
  logic m_axis_tvalid;
  logic m_axis_tready = 0;
  logic rxd = 1;
  logic [15:0] prescale = PRESCALE;
  logic rx_busy;
  logic rx_overrun_error;
  logic rx_frame_error;
  logic [7:0] s_axis_tdata = 0;
  logic s_axis_tvalid = 0;
  logic s_axis_tready;
  logic txd;
  logic tx_busy;

  always #(CLK_PERIOD / 2) clk = ~clk;

  uart #(.DATA_WIDTH(8)) dut (
    .clk(clk),
    .rst(rst),
    .s_axis_tdata(s_axis_tdata),
    .s_axis_tvalid(s_axis_tvalid),
    .s_axis_tready(s_axis_tready),
    .m_axis_tdata(m_axis_tdata),
    .m_axis_tvalid(m_axis_tvalid),
    .m_axis_tready(m_axis_tready),
    .rxd(rxd),
    .txd(txd),
    .tx_busy(tx_busy),
    .rx_busy(rx_busy),
    .rx_overrun_error(rx_overrun_error),
    .rx_frame_error(rx_frame_error),
    .prescale(prescale)
  );

  task automatic wait_clks(input int n);
    repeat (n) @(negedge clk);
  endtask

  task automatic do_reset();
    rst = 1;
    wait_clks(4);
    rst = 0;
    wait_clks(2);
  endtask

  initial begin
    m_axis_tready = 0;
    rxd = 1;
    s_axis_tdata = 0;
    s_axis_tvalid = 0;
    prescale = PRESCALE;

    do_reset();

    // ---- Frame 1: data 0x3C, good stop bit, sink stalled (tready=0) ----
    // After this frame m_axis_tvalid=1, m_axis_tdata=0x3C, held unread.
    rxd = 0;
    wait_clks(int'(prescale) * 8);
    for (int i = 0; i < 8; i++) begin
      rxd = (8'h3C >> i) & 1'b1;
      wait_clks(int'(prescale) * 8);
    end
    rxd = 1;
    wait_clks(int'(prescale) * 8);

    // Wait until the word is presented on the AXI output
    do @(negedge clk); while (!m_axis_tvalid);
    if (m_axis_tdata !== 8'h3C) begin
      $display("FAIL: unexpected tdata 0x%02h", m_axis_tdata);
      $finish;
    end

```
