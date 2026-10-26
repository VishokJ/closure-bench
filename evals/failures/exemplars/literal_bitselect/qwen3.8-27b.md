# literal_bitselect: qwen/qwen3.8-27b

Rollout `qwen3.8-27b/R23/0` (/Users/vishokj/Developer/cb-probe/outputs/official/qwen/closure-bench--qwen--qwen3.8-27b--null--ec46d01c/traces.jsonl:37), task R23, grade status `compile_error`. Picked as the median submission length (2945 chars) of 7 rollouts in this category for this model.

Sub-label: `None`

## Evidence

```json
{
 "categories_in_log": {
  "literal_bitselect": 2
 },
 "diagnostic": "%Error: <work>/submission/tb.sv:62:18: syntax error, unexpected '[', expecting ';'",
 "fatal_errors": 2,
 "literal": "8'h00[",
 "source_line": "rxd = 8'h00[i];"
}
```

## Gold excerpt (formal witness)

```systemverilog
// gold_source: formal
// closure_core.formal.cover_witness: depth 174, input_changes 10, bound 300, witness 9a44b3b1f01aa5fd
// Formal witness for R23_recover_after_frame_error_idle (closure_core/formal.py): the shortest legal input
// trace Yosys/SymbiYosys found (174 cycles), replayed on the uart_rx ports.
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
    repeat (76) @(negedge clk);
    rxd = 1'd1;
    repeat (18) @(negedge clk);
    rxd = 1'd0;
    repeat (4) @(negedge clk);
    rxd = 1'd1;
    repeat (15) @(negedge clk);
    rxd = 1'd0;
    repeat (8) @(negedge clk);
    rxd = 1'd1;
    @(negedge clk);
    rxd = 1'd0;
    repeat (18) @(negedge clk);
    rxd = 1'd1;
    repeat (7) @(negedge clk);
    rxd = 1'd0;
    repeat (8) @(negedge clk);
    rxd = 1'd1;
    repeat (19) @(negedge clk);
    $finish;
  end
endmodule
```

Event logs and divergence: not replayed (only miss, self_check_failed and never_finishes are).

## Submission excerpt

```systemverilog
`timescale 1ns / 1ps

module tb;

  localparam int CLK_PERIOD = 8;
  localparam logic [15:0] PRESCALE = 16'd5;
  localparam int BIT_CLKS = 40;  // prescale * 8

  logic        clk = 1'b0;
  logic        rst = 1'b0;
  logic [7:0]  s_axis_tdata = '0;
  logic        s_axis_tvalid = 1'b0;
  wire         s_axis_tready;
  wire  [7:0]  m_axis_tdata;
  wire         m_axis_tvalid;
  logic        m_axis_tready;
  logic        rxd = 1'b1;
  wire         txd;
  wire         tx_busy;
  wire         rx_busy;
  wire         rx_overrun_error;
  wire         rx_frame_error;
  logic [15:0] prescale = PRESCALE;

  always #(CLK_PERIOD / 2) clk = ~clk;

  uart #(.DATA_WIDTH(8)) dut (
    .clk(clk), .rst(rst),
    .s_axis_tdata(s_axis_tdata), .s_axis_tvalid(s_axis_tvalid),
    .s_axis_tready(s_axis_tready),
    .m_axis_tdata(m_axis_tdata), .m_axis_tvalid(m_axis_tvalid),
    .m_axis_tready(m_axis_tready),
    .rxd(rxd), .txd(txd),
    .tx_busy(tx_busy), .rx_busy(rx_busy),
    .rx_overrun_error(rx_overrun_error),
    .rx_frame_error(rx_frame_error),
    .prescale(prescale)
  );

  task automatic wait_clks(input int n);
    repeat (n) @(negedge clk);
  endtask

  task automatic do_reset();
    rst = 1'b1;
    wait_clks(4);
    rst = 1'b0;
    wait_clks(4);
  endtask

  initial begin
    m_axis_tready = 1'b1;
    do_reset();
    wait_clks(10);

    // === Error frame: stop bit = 0 to generate frame_error ===
    // Start bit
    rxd = 1'b0;
    wait_clks(BIT_CLKS);
    // 8 data bits (8'h00, LSB first)
    for (int i = 0; i < 8; i++) begin
      rxd = 8'h00[i];
      wait_clks(BIT_CLKS);
    end
    // Stop bit = 0 for 10 clocks: the DUT samples the stop bit at roughly
    // the 11th posedge of this period (rxd_reg=0 -> frame_error), then on
    // the very next posedge rxd is already 1 so the receiver does NOT
    // immediately latch a new start bit.
    rxd = 1'b0;
    wait_clks(10);
    rxd = 1'b1;

    // Wait for the 1-cycle frame_error pulse plus >=16 idle clocks
    // (busy=0, rxd=1) so cov_R23 reaches st==2 with cnt>=16.
    wait_clks(20);

    // === Valid frame: data = 8'hA5, stop bit = 1 ===
    // Hold m_axis_tready low so tvalid stays asserted after delivery.
    m_axis_tready = 1'b0;
    // Start bit
```
