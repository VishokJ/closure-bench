# self_check_failed: nvidia/nemotron-3-nano-30b-a3b

Rollout `nemotron-3-nano-30b-a3b/R19/0` (/Users/vishokj/Developer/cb-probe/outputs/official/nemotron/closure-bench--nvidia--nemotron-3-nano-30b-a3b--null--aded5d0b/traces.jsonl:6), task R19, grade status `runtime_error`. Picked as the median submission length (4079 chars) of 2 rollouts in this category for this model.

Sub-label: `watchdog`

## Evidence

```json
{
 "diagnostic": "Assertion failed in TOP.tb.wait_for_frame_error: frame_error never asserted",
 "first_divergence": {
  "gold_event": "cycle 3 rx busy_rise 0",
  "index": 0,
  "prescale": {
   "gold": [
    1
   ],
   "submission": []
  },
  "reason": "missing",
  "sequence": {
   "gold_event": "cycle 3 rx busy_rise 0",
   "index": 0,
   "matched_before": 0,
   "of": 2
  },
  "submission_cycles": []
 },
 "line": 71,
 "replay": {
  "gold_status": "ok",
  "gold_target_hits": {
   "R19": 1
  },
  "matches_trace": true,
  "status": "runtime_error",
  "target_hits": {
   "R19": 0
  }
 }
}
```

Residual label: **unclear**: The submission never instantiates uart_rx, so its log has no events at all (not even gold's `3 35000 rx busy_rise 0` or `154 1545000 rx frame_error 1`) and the undriven frame_error trips $error; a missing DUT instance fits none of the timing, sequence, data or protocol labels.

## Gold excerpt (formal witness)

```systemverilog
// gold_source: formal
// closure_core.formal.cover_witness: depth 156, input_changes 5, bound 300, witness bce8c505a7cbe1c9
// Formal witness for R19_frame_error_with_pending_word (closure_core/formal.py): the shortest legal input
// trace Yosys/SymbiYosys found (156 cycles), replayed on the uart_rx ports.
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
    repeat (25) @(negedge clk);
    rxd = 1'd1;
    repeat (29) @(negedge clk);
    rxd = 1'd0;
    repeat (20) @(negedge clk);
    rxd = 1'd1;
    repeat (2) @(negedge clk);
    rxd = 1'd0;
    repeat (80) @(negedge clk);
    $finish;
  end
endmodule
```

## Gold event log

```
1 15000 rx prescale 1
3 35000 rx busy_rise 0
154 1545000 rx frame_error 1
```

## Submission event log

```
(no events)
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
  "submission": []
 },
 "reason": "missing",
 "sequence": {
  "gold_event": "cycle 3 rx busy_rise 0",
  "index": 0,
  "matched_before": 0,
  "of": 2
 },
 "submission_cycles": []
}
```

## Submission excerpt

```systemverilog
`timescale 1ns / 1ps
module tb;

  // ------------------------------------------------------------
  // Parameters
  // ------------------------------------------------------------
  localparam int CLK_PERIOD   = 8;                // 125 MHz clock
  localparam logic [15:0] PRESCALE_VAL = 16'd5;   // preset prescale value

  // ------------------------------------------------------------
  // Clock and reset
  // ------------------------------------------------------------
  logic clk = 1'b0;
  logic rst = 1'b0;
  logic rxd = 1'b1;                               // UART_RX input
  logic [15:0] prescale_val = PRESCALE_VAL;       // configuration to DUT

  // ------------------------------------------------------------
  // DUT ports (uart_rx)
  // ------------------------------------------------------------
  logic [7:0]  m_axis_tdata;
  logic        m_axis_tvalid;
  logic        m_axis_tready;
  logic        busy;
  logic        overrun_error;
  logic        frame_error;

  // ------------------------------------------------------------
  // Clock generation
  // ------------------------------------------------------------
  always #(CLK_PERIOD/2) clk = ~clk;

  // ------------------------------------------------------------
  // Helper tasks
  // ------------------------------------------------------------
  // Wait for N falling‑edge clock cycles
  task automatic wait_n_clks (input int n);
    repeat (n) @(negedge clk);
  endtask

  // Transmit one UART frame (8N1)
  //   data_byte – byte to be sent (LSB first)
  //   stop_low  – 1 => stop bit forced low (causes frame_error)
  task automatic send_frame (input byte unsigned data_byte, input bit stop_low);
    // --- start bit (low) ---
    rxd = 1'b0;
    wait_n_clks(int'(PRESCALE_VAL) * 8);

    // --- data bits LSB first ---
    for (int i = 0; i < 8; i = i + 1) begin
      rxd = data_byte[i];
      wait_n_clks(int'(PRESCALE_VAL) * 8);
    end

    // --- stop bit ---
    rxd = stop_low ? 1'b0 : 1'b1;
    wait_n_clks(int'(PRESCALE_VAL) * 8);

    // Return line to idle state
    rxd = 1'b1;
  endtask

  // Wait until frame_error becomes asserted (polling timeout)
  task automatic wait_for_frame_error;
    int unsigned limit = 1000;
    while (frame_error == 1'b0 && limit != 0) begin
      wait_n_clks(1);
      limit = limit - 1;
    end
    if (frame_error !== 1'b1) begin
      $error("frame_error never asserted");
    end
  endtask

  // ------------------------------------------------------------
  // Reset sequence and stimulus
  // ------------------------------------------------------------
  initial begin
    // --- initial reset -------------------------------------------------
    rst = 1'b1;
```
