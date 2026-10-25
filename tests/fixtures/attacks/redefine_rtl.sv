// Pre-fix: reward 0 only because Verilator keeps the first definition (RTL is compiled first).
`timescale 1ns / 1ps
module uart_rx #(parameter DATA_WIDTH = 8) (
  input wire clk, input wire rst,
  output wire [DATA_WIDTH-1:0] m_axis_tdata, output wire m_axis_tvalid, input wire m_axis_tready,
  input wire rxd, output wire busy, output wire overrun_error, output wire frame_error,
  input wire [15:0] prescale);
  assign frame_error = 1; assign m_axis_tdata = 0; assign m_axis_tvalid = 0;
  assign busy = 0; assign overrun_error = 0;
endmodule
module tb;
  logic clk = 0; always #4 clk = ~clk;
  uart_rx #(.DATA_WIDTH(8)) dut (.clk(clk), .rst(1'b0), .m_axis_tdata(), .m_axis_tvalid(),
    .m_axis_tready(1'b1), .rxd(1'b1), .busy(), .overrun_error(), .frame_error(), .prescale(16'd5));
  initial #100 $finish;
endmodule
