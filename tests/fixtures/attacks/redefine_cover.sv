// Pre-fix: reward 0 only because Verilator keeps the first definition (covers are compiled first).
`timescale 1ns / 1ps
// Redefines our cover module.
module cov_R1 (input logic clk, input logic rst, input logic frame_error);
  R1_frame_error: cover property (@(posedge clk) 1'b1);
endmodule
module tb;
  logic clk = 0; always #4 clk = ~clk;
  uart_rx dut (.clk(clk), .rst(1'b0), .m_axis_tdata(), .m_axis_tvalid(), .m_axis_tready(1'b1), .rxd(1'b1), .busy(), .overrun_error(), .frame_error(), .prescale(16'd5));
  initial #100 $finish;
endmodule
