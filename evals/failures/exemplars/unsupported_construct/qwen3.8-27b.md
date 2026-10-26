# unsupported_construct: qwen/qwen3.8-27b

Rollout `qwen3.8-27b/R28/3` (/Users/vishokj/Developer/cb-probe/outputs/official/qwen/closure-bench--qwen--qwen3.8-27b--null--ec46d01c/traces.jsonl:74), task R28, grade status `compile_error`. Picked as the median submission length (2680 chars) of 2 rollouts in this category for this model.

Sub-label: `void cast`

## Evidence

```json
{
 "categories_in_log": {
  "other_syntax": 2,
  "unsupported_construct": 1
 },
 "diagnostic": "%Error: <work>/submission/tb.sv:57:18: syntax error, unexpected void",
 "fatal_errors": 3,
 "source_line": "task automatic void wait_clks(input int n);"
}
```

## Gold excerpt (formal witness)

```systemverilog
// gold_source: formal
// closure_core.formal.cover_witness: depth 160, input_changes 15, bound 300, witness 0e45509f2bad8ba0
// Formal witness for R28_pending_word_survives_false_start (closure_core/formal.py): the shortest legal input
// trace Yosys/SymbiYosys found (160 cycles), replayed on the uart_rx ports.
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
    repeat (23) @(negedge clk);
    rxd = 1'd1;
    repeat (36) @(negedge clk);
    rxd = 1'd0;
    repeat (16) @(negedge clk);
    rxd = 1'd1;
    @(negedge clk);
    rxd = 1'd0;
    @(negedge clk);
    rxd = 1'd1;
    repeat (3) @(negedge clk);
    rxd = 1'd0;
    repeat (10) @(negedge clk);
    rxd = 1'd1;
    repeat (6) @(negedge clk);
    rxd = 1'd0;
    @(negedge clk);
    m_axis_tready = 1'd1;
    repeat (10) @(negedge clk);
    rxd = 1'd1;
    repeat (5) @(negedge clk);
    rxd = 1'd0;
    repeat (12) @(negedge clk);
    rxd = 1'd1;
    repeat (14) @(negedge clk);
    rxd = 1'd0;
    repeat (6) @(negedge clk);
    rxd = 1'd1;
    repeat (16) @(negedge clk);
    $finish;
  end
endmodule
```

Event logs and divergence: not replayed (only miss, self_check_failed and never_finishes are).

## Submission excerpt

```systemverilog
`timescale 1ns / 1ps

module tb;

  localparam int CLK_PERIOD   = 8;
  localparam int PRESCALE_VAL = 5;
  localparam int BIT_CLKS     = PRESCALE_VAL * 8;

  logic        clk  = 1'b0;
  logic        rst  = 1'b1;
  logic [15:0] prescale = 16'd5;

  // AXI-Stream transmit side (kept idle)
  logic [7:0]  s_axis_tdata  = 8'h00;
  logic        s_axis_tvalid = 1'b0;
  wire         s_axis_tready;
  wire         txd;
  wire         tx_busy;

  // AXI-Stream receive side
  wire [7:0]  m_axis_tdata;
  wire        m_axis_tvalid;
  logic       m_axis_tready = 1'b0;

  // UART pins
  logic rxd = 1'b1;

  wire rx_busy;
  wire rx_overrun_error;
  wire rx_frame_error;

  always #(CLK_PERIOD / 2) clk = ~clk;

  uart dut (
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

  task automatic void wait_clks(input int n);
    repeat (n) @(negedge clk);
  endtask

  task automatic void do_reset();
    rst = 1'b1;
    wait_clks(2);
    rst = 1'b0;
    wait_clks(2);
  endtask

  // Send an 8N1 byte on rxd.  Each bit is held for prescale * 8 clocks.
  task automatic void rx_send_byte(input logic [7:0] b);
    rxd = 1'b0;
    wait_clks(BIT_CLKS);

    for (int i = 0; i < 8; i++) begin
      rxd = b[i];
      wait_clks(BIT_CLKS);
    end

    rxd = 1'b1;
    wait_clks(BIT_CLKS);
  endtask
```
