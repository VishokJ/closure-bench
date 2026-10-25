// Pre-fix: allowed. Now rejected: defparam changes DATA_WIDTH (covers assume the default).
`timescale 1ns / 1ps
module tb;
  logic clk = 0; always #4 clk = ~clk;
  uart_rx dut (.clk(clk), .rst(1'b0), .m_axis_tdata(), .m_axis_tvalid(), .m_axis_tready(1'b1), .rxd(1'b1), .busy(), .overrun_error(), .frame_error(), .prescale(16'd5));
  defparam dut.DATA_WIDTH = 4;
  initial #100 $finish;
endmodule
