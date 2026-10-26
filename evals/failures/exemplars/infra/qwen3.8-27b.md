# infra: qwen/qwen3.8-27b

Rollout `qwen3.8-27b/R26/6` (/Users/vishokj/Developer/cb-probe/outputs/official/qwen/closure-bench--qwen--qwen3.8-27b--null--ec46d01c/traces.jsonl:156), task R26, grade status `compile_error`. Picked as the median submission length (3283 chars) of 3 rollouts in this category for this model.

Sub-label: `verilator_internal`

## Evidence

```json
{
 "diagnostic": "%Error: Internal Error: <work>/submission/tb.sv:79:7: ../V3Ast.h:2359: AstNode is not of expected type, but instead has type 'IF'"
}
```

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

Event logs and divergence: not replayed (only miss, self_check_failed and never_finishes are).

## Submission excerpt

```systemverilog
`timescale 1ns / 1ps

module tb;

  localparam int CLK_PERIOD = 8;
  localparam logic [15:0] PRESCALE = 16'd5;

  logic        clk = 1'b0;
  logic        rst = 1'b0;
  logic [7:0]  s_axis_tdata = '0;
  logic        s_axis_tvalid = 1'b0;
  logic        m_axis_tready = 1'b0;
  logic        rxd = 1'b1;
  logic [15:0] prescale = PRESCALE;
  wire         s_axis_tready;
  wire  [7:0]  m_axis_tdata;
  wire         m_axis_tvalid;
  wire         txd;
  wire         tx_busy;
  wire         rx_busy;
  wire         rx_overrun_error;
  wire         rx_frame_error;

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

  task automatic wait_clks(input int n);
    repeat (n) @(negedge clk);
  endtask

  task automatic do_reset();
    rst = 1'b0; wait_clks(2);
    rst = 1'b1; wait_clks(2);
    rst = 1'b0; wait_clks(2);
  endtask

  // Send a valid 8N1 frame on rxd (stop bit high)
  task automatic uart_send_valid(input logic [7:0] b);
    int bit_clks = int'(prescale) * 8;
    rxd = 1'b0;    wait_clks(bit_clks);
    for (int i = 0; i < 8; i++) begin
      rxd = b[i];  wait_clks(bit_clks);
    end
    rxd = 1'b1;    wait_clks(bit_clks);
  endtask

  // Send a frame whose stop bit is low to generate a frame_error pulse
  task automatic uart_send_frame_error(input logic [7:0] b);
    int bit_clks = int'(prescale) * 8;
    rxd = 1'b0;    wait_clks(bit_clks);
    for (int i = 0; i < 8; i++) begin
      rxd = b[i];  wait_clks(bit_clks);
    end
    rxd = 1'b0;    wait_clks(bit_clks);  // bad stop bit (low)
    rxd = 1'b1;    wait_clks(bit_clks);  // return line to idle
  endtask

  task automatic wait_until_valid();
    int cnt = 0;
    while (!m_axis_tvalid) begin
      @(negedge clk);
      if (++cnt > 2000) $fatal(1, "timeout waiting for m_axis_tvalid");
    end
```
