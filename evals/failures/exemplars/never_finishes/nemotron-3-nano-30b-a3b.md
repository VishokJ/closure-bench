# never_finishes: nvidia/nemotron-3-nano-30b-a3b

Rollout `nemotron-3-nano-30b-a3b/R27/7` (/Users/vishokj/Developer/cb-probe/outputs/official/nemotron/closure-bench--nvidia--nemotron-3-nano-30b-a3b--null--aded5d0b/traces.jsonl:208), task R27, grade status `timeout`. Picked as the median submission length (3604 chars) of 21 rollouts in this category for this model.

Sub-label: `timeout`

## Evidence

```json
{
 "first_divergence": {
  "gold_event": "cycle 3 rx busy_rise 0",
  "index": 0,
  "prescale": {
   "gold": [
    1,
    1
   ],
   "submission": [
    5,
    5
   ]
  },
  "reason": "at a different cycle",
  "sequence": {
   "gold_event": "cycle 3 rx busy_rise 0",
   "index": 1,
   "matched_before": 1,
   "of": 4
  },
  "submission_cycles": [
   21
  ]
 },
 "last_log_line": null,
 "replay": {
  "gold_status": "ok",
  "gold_target_hits": {
   "R27": 1
  },
  "matches_trace": true,
  "status": "timeout",
  "target_hits": {
   "R27": 0
  }
 },
 "run_s": 60.0,
 "status": "timeout"
}
```

Residual label: **wrong_sequence**: The second initial block's wait(!rst) passes at time 0, so the 0x5A frame overlaps the first frame (sub `21 328000 rx busy_rise 0`) instead of following the reset; after the reset (sub `1 5624000 rx prescale 5`) no new frame is ever sent, so gold's `78 1555000 rx hs 5a` never occurs and the testbench hangs waiting for tvalid.

## Gold excerpt (formal witness)

```systemverilog
// gold_source: formal
// closure_core.formal.cover_witness: depth 157, input_changes 12, bound 300, witness fd43632100ba1367
// Formal witness for R27_rx_rst_at_stop_sample (closure_core/formal.py): the shortest legal input
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
    repeat (20) @(negedge clk);
    rxd = 1'd1;
    repeat (56) @(negedge clk);
    rst = 1'd1;
    @(negedge clk);
    rst = 1'd0; rxd = 1'd0;
    repeat (19) @(negedge clk);
    rxd = 1'd1;
    repeat (5) @(negedge clk);
    rxd = 1'd0;
    repeat (11) @(negedge clk);
    rxd = 1'd1;
    repeat (9) @(negedge clk);
    rxd = 1'd0;
    repeat (12) @(negedge clk);
    rxd = 1'd1;
    repeat (5) @(negedge clk);
    rxd = 1'd0;
    repeat (11) @(negedge clk);
    rxd = 1'd1;
    repeat (8) @(negedge clk);
    $finish;
  end
endmodule
```

## Gold event log

```
1 15000 rx prescale 1
3 35000 rx busy_rise 0
1 785000 rx prescale 1
3 805000 rx busy_rise 0
78 1555000 rx hs 5a
79 1565000 rx busy_fall 0
```

## Submission event log

```
1 8000 rx prescale 5
21 328000 rx busy_rise 0
1 5624000 rx prescale 5
```

## First divergence

```json
{
 "gold_event": "cycle 3 rx busy_rise 0",
 "index": 0,
 "prescale": {
  "gold": [
   1,
   1
  ],
  "submission": [
   5,
   5
  ]
 },
 "reason": "at a different cycle",
 "sequence": {
  "gold_event": "cycle 3 rx busy_rise 0",
  "index": 1,
  "matched_before": 1,
  "of": 4
 },
 "submission_cycles": [
  21
 ]
}
```

## Submission excerpt

```systemverilog
module tb;
  // -------------------------------------------------
  // Clock generation
  logic clk = 0;
  initial begin
    forever #(8) clk = ~clk;   // 125 MHz
  end

  // -------------------------------------------------
  // DUT signals
  logic        rst      = 0;
  logic        rxd      = 1;
  logic [15:0] prescale = 16'd5;   // preset value (non‑zero)

  logic        busy;
  logic        overrun_error;
  logic        frame_error;
  logic        m_axis_tvalid;
  logic [7:0]  m_axis_tdata;
  logic        m_axis_tready;

  // AXI‐stream sink is always ready
  assign m_axis_tready = 1'b1;

  // -------------------------------------------------
  // Instantiate the RX module (default DATA_WIDTH = 8)
  uart_rx #(.DATA_WIDTH(8)) dut (
    .clk          (clk),
    .rst          (rst),
    .m_axis_tdata (m_axis_tdata),
    .m_axis_tvalid(m_axis_tvalid),
    .m_axis_tready(m_axis_tready),
    .rxd          (rxd),
    .busy         (busy),
    .overrun_error(overrun_error),
    .frame_error  (frame_error),
    .prescale     (prescale)
  );

  // -------------------------------------------------
  // Timing constants (prescale = 5 → 18 init cycles, 39 cycles per bit)
  localparam int PRESCALE_VAL = 5;
  localparam int INITIAL_WAIT = (PRESCALE_VAL << 2) - 2; // 18
  localparam int WAIT_BIT    = (PRESCALE_VAL << 3) - 1;  // 39
  localparam int TOTAL_CYCLES = INITIAL_WAIT + 8 * WAIT_BIT; // 330

  // -------------------------------------------------
  // Task: transmit a byte and finish when 0x5A is received
  task automatic send_frame_byte(input logic [7:0] data);
    // Wait until the DUT is idle
    wait (!busy);

    // Drive start bit (low for one cycle)
    rxd = 0;
    @(posedge clk);

    // Wait until the first data‑bit sampling instant
    repeat (INITIAL_WAIT) @(posedge clk);

    // Send 8 data bits, MSB‑first
    for (int i = 7; i >= 0; i--) begin
      if (i != 7) begin
        repeat (WAIT_BIT) @(posedge clk);
      end
      rxd = data[i];
    end

    // One more bit period before the stop bit
    repeat (WAIT_BIT) @(posedge clk);
    // Drive stop bit (high)
    rxd = 1;
    // Hold stop high for one bit period
    repeat (WAIT_BIT) @(posedge clk);

    // Wait for the generated AXI‑stream word
    wait (m_axis_tvalid && m_axis_tdata == 8'h5A);
    $finish;
  endtask

  // -------------------------------------------------
```
