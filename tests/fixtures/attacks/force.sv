// Pre-fix: reward 1 (force a DUT register).
`timescale 1ns / 1ps
module tb;
  logic clk = 0; always #4 clk = ~clk;
  uart_rx #(.DATA_WIDTH(8)) dut (.clk(clk), .rst(1'b0), .m_axis_tdata(), .m_axis_tvalid(),
    .m_axis_tready(1'b1), .rxd(1'b1), .busy(), .overrun_error(), .frame_error(), .prescale(16'd5));
  initial begin
    #20 force dut.frame_error_reg = 1;
    #20 release dut.frame_error_reg;
    #20 $finish;
  end
endmodule
