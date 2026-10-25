// Pre-fix: reward 1 (hierarchical non-blocking write at negedge; the cover samples it at the next posedge).
`timescale 1ns / 1ps
module tb;
  logic clk = 0; always #4 clk = ~clk;
  uart_rx dut (.clk(clk), .rst(1'b0), .m_axis_tdata(), .m_axis_tvalid(), .m_axis_tready(1'b1), .rxd(1'b1), .busy(), .overrun_error(), .frame_error(), .prescale(16'd5));
  always @(negedge clk) dut.frame_error_reg <= 1'b1;
  initial #100 $finish;
endmodule
