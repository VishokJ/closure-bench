// c03 with overrun_error added as an input port that is never read (repair-loop trick).
module cov_P3 (
  input logic        clk,
  input logic        rst,
  input logic        m_axis_tvalid,
  input logic        m_axis_tready,
  input logic [7:0]  m_axis_tdata,
  input logic [7:0]  data_reg,
  input logic [3:0]  bit_cnt,
  input logic [18:0] prescale_reg,
  input logic        rxd_reg,
  input logic        overrun_error   // added to satisfy description_sync; never read
);

  // Handshake of the pending word (0x3C) on the very edge where the next
  // frame's stop bit is sampled high with the new word (0xA5) assembled.
  P3_read_on_stop_edge: cover property (@(posedge clk) disable iff (rst)
    (bit_cnt == 4'd1) && (prescale_reg == 19'd0) && rxd_reg &&
    m_axis_tvalid && m_axis_tready &&
    (m_axis_tdata == 8'h3C) && (data_reg == 8'hA5));

endmodule

bind uart_rx cov_P3 u_cov_P3 (.*);
