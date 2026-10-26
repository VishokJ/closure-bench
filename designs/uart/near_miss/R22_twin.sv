// near_miss_source: formal witness of the twin cover; depth 156, bound 300, witness 6ade7d6ff3076fe5
// Formal witness for R22_twin_prescale1 (closure_core/formal.py): the shortest legal input
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
    repeat (17) @(negedge clk);
    rxd = 1'd1;
    repeat (4) @(negedge clk);
    rxd = 1'd0;
    repeat (20) @(negedge clk);
    rxd = 1'd1;
    repeat (5) @(negedge clk);
    rxd = 1'd0;
    repeat (22) @(negedge clk);
    rxd = 1'd1;
    repeat (8) @(negedge clk);
    rxd = 1'd0;
    repeat (27) @(negedge clk);
    rxd = 1'd1;
    repeat (2) @(negedge clk);
    rxd = 1'd0;
    repeat (12) @(negedge clk);
    rxd = 1'd1;
    repeat (15) @(negedge clk);
    rxd = 1'd0;
    repeat (19) @(negedge clk);
    rxd = 1'd1;
    repeat (5) @(negedge clk);
    $finish;
  end
endmodule
