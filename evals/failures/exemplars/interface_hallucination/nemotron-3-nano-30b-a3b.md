# interface_hallucination: nvidia/nemotron-3-nano-30b-a3b

Rollout `nemotron-3-nano-30b-a3b/R14/0` (/Users/vishokj/Developer/cb-probe/outputs/official/nemotron/closure-bench--nvidia--nemotron-3-nano-30b-a3b--null--aded5d0b/traces.jsonl:27), task R14, grade status `compile_error`. Picked as the median submission length (3836 chars) of 35 rollouts in this category for this model.

Sub-label: `busy`

## Evidence

```json
{
 "categories_in_log": {
  "interface_hallucination": 1
 },
 "diagnostic": "%Error-PINNOTFOUND: <work>/submission/tb.sv:46:6: Pin not found: 'busy'",
 "fatal_errors": 1,
 "kind": "pin",
 "module": "uart",
 "pinmissing": [
  "tx_busy"
 ],
 "real_ports": [
  "clk",
  "rst",
  "s_axis_tdata",
  "s_axis_tvalid",
  "s_axis_tready",
  "m_axis_tdata",
  "m_axis_tvalid",
  "m_axis_tready",
  "rxd",
  "txd",
  "tx_busy",
  "rx_busy",
  "rx_overrun_error",
  "rx_frame_error",
  "prescale"
 ],
 "source_line": ".busy              (tx_busy),"
}
```

## Gold excerpt (formal witness)

```systemverilog
// gold_source: formal
// closure_core.formal.cover_witness: depth 156, input_changes 10, bound 300, witness 921e03033e6c8788
// Formal witness for R14_short_stop_back_to_back (closure_core/formal.py): the shortest legal input
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
    repeat (51) @(negedge clk);
    rxd = 1'd1;
    repeat (25) @(negedge clk);
    rxd = 1'd0;
    repeat (14) @(negedge clk);
    rxd = 1'd1;
    repeat (13) @(negedge clk);
    rxd = 1'd0;
    repeat (8) @(negedge clk);
    rxd = 1'd1;
    repeat (16) @(negedge clk);
    rxd = 1'd0;
    @(negedge clk);
    rxd = 1'd1;
    repeat (8) @(negedge clk);
    rxd = 1'd0;
    repeat (8) @(negedge clk);
    rxd = 1'd1;
    repeat (12) @(negedge clk);
    $finish;
  end
endmodule
```

Event logs and divergence: not replayed (only miss, self_check_failed and never_finishes are).

## Submission excerpt

```systemverilog
module tb;
  // -------------------------------------------------
  // Clock and reset
  reg clk = 0;
  always #(8) clk = ~clk; // 125 MHz

  reg rst = 0;

  // -------------------------------------------------
  // Configuration (prescale = 5 as in baseline)
  localparam int PRESCALE_VAL = 16'd5;
  wire [15:0] prescale = PRESCALE_VAL;

  // -------------------------------------------------
  // UART interface signals
  reg rxd = 1'b1;

  // AXI‑Stream interface signals (only the_RX side is used)
  reg [7:0] s_axis_tdata = 0;
  reg s_axis_tvalid = 0;
  wire s_axis_tready; // output of DUT, not driven by TB
  wire m_axis_tdata;
  wire m_axis_tvalid;
  wire m_axis_tready; // input of DUT, kept high
  assign m_axis_tready = 1'b1;

  // UART status outputs
  wire txd;
  wire tx_busy;
  wire rx_busy;
  wire rx_overrun_error;
  wire rx_frame_error;

  // -------------------------------------------------
  // DUT instantiation (top‑level module must be named tb)
  uart dut (
    .clk               (clk),
    .rst               (rst),
    .s_axis_tdata      (s_axis_tdata),
    .s_axis_tvalid     (s_axis_tvalid),
    .s_axis_tready     (s_axis_tready),
    .m_axis_tdata      (m_axis_tdata),
    .m_axis_tvalid     (m_axis_tvalid),
    .m_axis_tready     (m_axis_tready),
    .txd               (txd),
    .busy              (tx_busy),
    .rx_busy           (rx_busy),
    .rx_overrun_error  (rx_overrun_error),
    .rx_frame_error    (rx_frame_error),
    .rxd               (rxd),
    .prescale          (prescale)
  );

  // -------------------------------------------------
  // Task: transmit a byte on rxd using the prescale setting
  task automatic send_uart_byte(input byte unsigned b);
    int bit_clks;
    bit_clks = int'(prescale) * 8;
    // start bit
    rxd = 0;
    repeat (bit_clks) @(negedge clk);
    // data bits (LSB first)
    for (int i = 0; i < 8; i++) begin
      rxd = b[i];
      repeat (bit_clks) @(negedge clk);
    end
    // stop bit
    rxd = 1;
    repeat (bit_clks) @(negedge clk);
  endtask

  // -------------------------------------------------
  // Coverage‑point stimulus
  reg first_word_rising = 0;
  reg [1:0] wait_counter = 0;
  reg second_frame_launched = 0;

  // Detect first word delivery (m_axis_tvalid rise), wait 2 clocks,
  // then transmit the second frame (0x5A) and finish when it completes.
  always @(posedge clk) begin
```
