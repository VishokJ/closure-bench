// Two consecutive words, 8'h12 then 8'h34, no frame_error in between; the
// second frame is received entirely at prescale 16'd2.
module cov_R22 (
  input logic        clk,
  input logic        rst,
  input logic [15:0] prescale,
  input logic [18:0] prescale_reg,
  input logic [3:0]  bit_cnt,
  input logic        rxd_reg,
  input logic [7:0]  data_reg,
  input logic        frame_error,
  input logic        m_axis_tvalid,
  input logic [7:0]  m_axis_tdata
);

  reg prev12;  // last delivered word was 8'h12, no frame_error since
  reg p2;      // current frame started and stayed at prescale 16'd2

  always @(posedge clk) begin
    if (rst) begin
      prev12 <= 1'b0;
      p2     <= 1'b0;
    end else begin
      if (frame_error) begin
        prev12 <= 1'b0;
      end
      if (bit_cnt == 4'd1 && prescale_reg == 19'd0 && rxd_reg) begin
        prev12 <= (data_reg == 8'h12);
      end
      if (bit_cnt == 4'd0 && prescale_reg == 19'd0 && !rxd_reg) begin
        p2 <= (prescale == 16'd2);
      end else if (prescale != 16'd2) begin
        p2 <= 1'b0;
      end
    end
  end

  R22_rx_prescale2_two_words: cover property (@(posedge clk) disable iff (rst)
    m_axis_tvalid && (m_axis_tdata == 8'h34) &&
    ($past(bit_cnt) == 4'd1) && ($past(prescale_reg) == 19'd0) && $past(rxd_reg) &&
    $past(prev12) && p2 && (prescale == 16'd2));

endmodule

bind uart_rx cov_R22 u_cov_R22 (.*);
