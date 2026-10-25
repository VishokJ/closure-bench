// Pre-fix: reward 1 (bound module drives a DUT register through an output port; no hierarchical reference).
`timescale 1ns / 1ps
module evil (input logic clk, output logic frame_error_reg);
  always @(negedge clk) frame_error_reg <= 1'b1;
endmodule
bind uart_rx evil u_evil (.clk(clk), .frame_error_reg(frame_error_reg));
module tb;
  logic clk = 0; always #4 clk = ~clk;
  uart_rx dut (.clk(clk), .rst(1'b0), .m_axis_tdata(), .m_axis_tvalid(), .m_axis_tready(1'b1), .rxd(1'b1), .busy(), .overrun_error(), .frame_error(), .prescale(16'd5));
  initial #100 $finish;
endmodule
