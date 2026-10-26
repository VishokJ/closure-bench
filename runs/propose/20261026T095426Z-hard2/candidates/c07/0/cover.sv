// Second overrun pulse while the sink never became ready: three frames
// completed back to back with no handshake; the output now holds 8'h5A.
module cov_P7 (
  input logic       clk,
  input logic       rst,
  input logic       overrun_error,
  input logic       m_axis_tvalid,
  input logic       m_axis_tready,
  input logic [7:0] m_axis_tdata
);

  // overrun_error pulses seen since m_axis_tready was last high (saturating)
  reg [1:0] ovr_cnt;

  always @(posedge clk) begin
    if (rst) begin
      ovr_cnt <= 2'd0;
    end else if (m_axis_tready) begin
      ovr_cnt <= 2'd0;
    end else if (overrun_error && ovr_cnt != 2'd3) begin
      ovr_cnt <= ovr_cnt + 2'd1;
    end
  end

  P7_rx_double_overrun_third_word: cover property (@(posedge clk) disable iff (rst)
    overrun_error && !m_axis_tready && (ovr_cnt == 2'd1) &&
    m_axis_tvalid && (m_axis_tdata == 8'h5A));

endmodule

bind uart_rx cov_P7 u_cov_P7 (.*);
