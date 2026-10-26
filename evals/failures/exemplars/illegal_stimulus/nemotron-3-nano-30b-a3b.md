# illegal_stimulus: nvidia/nemotron-3-nano-30b-a3b

Rollout `nemotron-3-nano-30b-a3b/T11/2` (/Users/vishokj/Developer/cb-probe/outputs/official/nemotron/closure-bench--nvidia--nemotron-3-nano-30b-a3b--null--aded5d0b/traces.jsonl:97), task T11, grade status `illegal_stimulus`. Picked as the median submission length (2625 chars) of 17 rollouts in this category for this model.

Sub-label: `axis_tvalid_low_in_reset`

## Evidence

```json
{
 "checker": "TOP.tb.dut.u_chk_legal",
 "diagnostic": "ILLEGAL_STIMULUS: axis_tvalid_low_in_reset at 84000 in TOP.tb.dut.u_chk_legal",
 "time": 84000
}
```

## Gold excerpt (formal witness)

```systemverilog
// gold_source: formal
// closure_core.formal.cover_witness: depth 157, input_changes 4, bound 300, witness 740436c57a3aed97
// Formal witness for T11_tvalid_rise_mid_frame (closure_core/formal.py): the shortest legal input
// trace Yosys/SymbiYosys found (157 cycles), replayed on the uart_tx ports.
// A gold candidate, never shown to an agent; Verilator decides whether it hits.
`timescale 1ns / 1ps

module tb;
  logic clk = 1'b0;
  always #5 clk = ~clk;
  logic rst = 1'd1;
  logic [7:0] s_axis_tdata = 8'd60;
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
    repeat (64) @(negedge clk);
    s_axis_tvalid = 1'd1;
    repeat (91) @(negedge clk);
    $finish;
  end
endmodule
```

Event logs and divergence: not replayed (only miss, self_check_failed and never_finishes are).

## Submission excerpt

```systemverilog
module tb;

  // ------------------------------------------------------------
  // Clock and reset
  // ------------------------------------------------------------
  logic clk = 0;
  initial begin
    forever #(4) clk = ~clk;  // 8‑ns period (125 MHz)
  end

  logic rst = 1;
  initial begin
    #40 rst = 0;
    #40 rst = 1;          // simple reset pulse
  end

  // ------------------------------------------------------------
  // DUT ports
  // ------------------------------------------------------------
  logic [7:0]  s_axis_tdata;
  logic        s_axis_tvalid;
  logic        s_axis_tready;
  logic        txd;
  logic        busy;
  logic [15:0] prescale;

  // Connect a constant non‑zero prescale value (5) – satisfies
  // all prescale‑related coverage checks.
  localparam logic [15:0] PRESCALE_VAL = 16'd5;
  assign prescale = PRESCALE_VAL;

  // ------------------------------------------------------------
  // Instantiate the transmitter (default parameters)
  // ------------------------------------------------------------
  uart_tx #(.DATA_WIDTH(8)) dut (
    .clk          (clk),
    .rst          (rst),
    .s_axis_tdata (s_axis_tdata),
    .s_axis_tvalid(s_axis_tvalid),
    .s_axis_tready(s_axis_tready),
    .txd          (txd),
    .busy         (busy),
    .prescale     (prescale)
  );

  // ------------------------------------------------------------
  // Testbench stimulus
  // ------------------------------------------------------------
  initial begin
    // ----- 1. Load a dummy word to put the TX engine into a busy state -----
    s_axis_tdata  = 8'hAA;
    s_axis_tvalid = 1'b1;
    @(posedge clk);
    s_axis_tvalid = 1'b0;      // one‑cycle pulse is enough to start a frame
    s_axis_tdata  = 8'h00;     // keep data stable

    // Wait a few cycles to be sure the transmitter is now busy
    repeat (10) @(posedge clk);

    // ----- 2. Assert the target word (8'h3C) while busy is high -------------
    s_axis_tdata  = 8'h3C;
    s_axis_tvalid = 1'b1;      // this rise occurs with busy==1 and 1 <= bit_cnt <= 8
    // Keep both signals stable; the coverage model will observe the
    // subsequent transmission of 8'h3C and fire the T11_tvalid_rise_mid_frame point.

    // Give the design enough time to finish the new frame and set `done`.
    // 1500 clock cycles are more than enough for two UART frames at prescale=5.
    repeat (1500) @(posedge clk);

    // ------------------------------------------------------------
    // Coverage point hit – end simulation cleanly
    // ------------------------------------------------------------
    $finish;
  end

endmodule
```
