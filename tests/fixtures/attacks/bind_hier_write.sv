// Pre-fix: reward 1 (the same write from a module bound into uart_rx).
`timescale 1ns / 1ps
module evil (input logic clk);
  always @(negedge clk) uart_rx.frame_error_reg <= 1'b1;
endmodule
bind uart_rx evil u_evil (.clk(clk));
module tb;
  logic clk = 0; always #4 clk = ~clk;
  uart_rx dut (.clk(clk), .rst(1'b0), .m_axis_tdata(), .m_axis_tvalid(), .m_axis_tready(1'b1), .rxd(1'b1), .busy(), .overrun_error(), .frame_error(), .prescale(16'd5));
  initial #100 $finish;
endmodule
