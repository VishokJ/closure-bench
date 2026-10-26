# miss: nvidia/nemotron-3-nano-30b-a3b

Rollout `nemotron-3-nano-30b-a3b/R21/2` (/Users/vishokj/Developer/cb-probe/outputs/official/nemotron/closure-bench--nvidia--nemotron-3-nano-30b-a3b--null--aded5d0b/traces.jsonl:23), task R21, grade status `ok`. Picked as the median submission length (3228 chars) of 38 rollouts in this category for this model.

Sub-label: `None`

## Evidence

```json
{
 "first_divergence": {
  "gold_event": "cycle 78 rx hs 69",
  "index": 1,
  "prescale": {
   "gold": [
    1
   ],
   "submission": [
    1,
    1
   ]
  },
  "reason": "missing",
  "sequence": {
   "gold_event": "cycle 78 rx hs 69",
   "index": 1,
   "matched_before": 1,
   "of": 4
  },
  "submission_cycles": []
 },
 "other_items_hit": [],
 "replay": {
  "gold_status": "ok",
  "gold_target_hits": {
   "R21": 1
  },
  "matches_trace": true,
  "status": "ok",
  "target_hits": {
   "R21": 0
  }
 },
 "target_hits": {
  "R21": 0
 }
}
```

Residual label: **protocol_misunderstanding**: The sub never drives m_axis_tready, so the first 0x69 word is never accepted: gold has `78 ... rx hs 69` while the sub frame only ends with `79 ... rx busy_fall 0`. The second frame then raises `157 ... rx overrun_error 1` instead of gold's `154 ... rx hs 96`, even though the frame timing is correct.

## Gold excerpt (formal witness)

```systemverilog
// gold_source: formal
// closure_core.formal.cover_witness: depth 156, input_changes 14, bound 300, witness 38c2dcde3ec2a2e9
// Formal witness for R21_rx_min_prescale_two_words (closure_core/formal.py): the shortest legal input
// trace Yosys/SymbiYosys found (156 cycles), replayed on the uart_rx ports.
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
    repeat (8) @(negedge clk);
    rxd = 1'd1;
    repeat (4) @(negedge clk);
    rxd = 1'd0;
    repeat (22) @(negedge clk);
    rxd = 1'd1;
    repeat (4) @(negedge clk);
    rxd = 1'd0;
    repeat (12) @(negedge clk);
    rxd = 1'd1;
    repeat (10) @(negedge clk);
    rxd = 1'd0;
    repeat (8) @(negedge clk);
    rxd = 1'd1;
    repeat (8) @(negedge clk);
    rxd = 1'd0;
    repeat (19) @(negedge clk);
    rxd = 1'd1;
    repeat (11) @(negedge clk);
    rxd = 1'd0;
    repeat (13) @(negedge clk);
    rxd = 1'd1;
    repeat (2) @(negedge clk);
    rxd = 1'd0;
    repeat (22) @(negedge clk);
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
78 785000 rx hs 69
154 1545000 rx hs 96
155 1555000 rx busy_fall 0
```

## Submission event log

```
1 204000 tx prescale 1
1 204000 rx prescale 1
3 220000 rx busy_rise 0
79 828000 rx busy_fall 0
82 852000 rx busy_rise 0
157 1452000 rx overrun_error 1
158 1460000 rx busy_fall 0
```

## First divergence

```json
{
 "gold_event": "cycle 78 rx hs 69",
 "index": 1,
 "prescale": {
  "gold": [
   1
  ],
  "submission": [
   1,
   1
  ]
 },
 "reason": "missing",
 "sequence": {
  "gold_event": "cycle 78 rx hs 69",
  "index": 1,
  "matched_before": 1,
  "of": 4
 },
 "submission_cycles": []
}
```

## Submission excerpt

```systemverilog
module tb;

  // ------------------------------------------------------------
  // Clock and reset
  // ------------------------------------------------------------
  logic        clk = 0;
  logic        rst   = 1'b1;
  // 8‑bit UART data bus
  logic [7:0]  s_axis_tdata;
  logic        s_axis_tvalid;
  logic        s_axis_tready;
  logic [7:0]  m_axis_tdata;
  logic        m_axis_tvalid;
  logic        m_axis_tready;
  // UART interface
  logic        rxd;
  // Configuration
  logic [15:0] prescale = 16'd1;   // minimum prescale

  // ------------------------------------------------------------
  // Clock generation (period = 8 time units → 125 MHz)
  // ------------------------------------------------------------
  initial clk = 1'b0;
  always #4 clk = ~clk;

  // ------------------------------------------------------------
  // DUT instantiation (default parameters)
  // ------------------------------------------------------------
  uart dut (
    .clk               (clk),
    .rst               (rst),
    .s_axis_tdata      (s_axis_tdata),
    .s_axis_tvalid     (s_axis_tvalid),
    .s_axis_tready     (s_axis_tready),
    .m_axis_tdata      (m_axis_tdata),
    .m_axis_tvalid     (m_axis_tvalid),
    .m_axis_tready     (m_axis_tready),
    .rxd               (rxd),
    .txd               (),          // not used
    .tx_busy           (),
    .rx_busy           (),
    .rx_overrun_error  (),
    .rx_frame_error    (),
    .prescale          (prescale)
  );

  // ------------------------------------------------------------
  // Tie‑off TX side (idle)
  // ------------------------------------------------------------
  assign s_axis_tready = 1'b1;
  assign s_axis_tvalid = 1'b0;
  assign s_axis_tdata  = 8'h00;

  // ------------------------------------------------------------
  // Reset sequence
  // ------------------------------------------------------------
  initial begin
    #100 rst = 1'b1;
    #100 rst = 1'b0;
    #100;
  end

  // ------------------------------------------------------------
  // Task: send one UART frame (start, 8 data bits LSB first, stop)
  // ------------------------------------------------------------
  task automatic send_frame(input byte data);
    // 10 bit periods per frame, each period = 8 clocks (prescale = 1)
    for (int bp = 0; bp < 10; bp++) begin
      if (bp == 0)       rxd <= 1'b0;                     // start bit
      else if (bp >= 1 && bp <= 8)
                         rxd <= data[bp-1];                 // data bits
      else               rxd <= 1'b1;                     // stop bit
      // wait one full bit period (8 clock cycles)
      repeat (8) @(posedge clk);
    end
  endtask

  // ------------------------------------------------------------
  // Apply two back‑to‑back frames: 0x69 then 0x96
  // ------------------------------------------------------------
```
