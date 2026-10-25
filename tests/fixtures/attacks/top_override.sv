// Override through the uart top: specialises uart_rx and uart_tx inside the design.
`timescale 1ns / 1ps
module tb;
  logic clk = 0; always #4 clk = ~clk;
  uart #(.DATA_WIDTH(9)) u (.clk(clk), .rst(1'b0), .s_axis_tdata(9'd0), .s_axis_tvalid(1'b0), .s_axis_tready(),
    .m_axis_tdata(), .m_axis_tvalid(), .m_axis_tready(1'b1), .rxd(1'b1), .txd(), .tx_busy(), .rx_busy(),
    .rx_overrun_error(), .rx_frame_error(), .prescale(16'd5));
  initial #100 $finish;
endmodule
