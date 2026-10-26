// A frame error occurs while 8'h3C is held unread under back-pressure; then a
// good frame overruns it with 8'hA5.
module cov_R26 (
  input logic       clk,
  input logic       rst,
  input logic       frame_error,
  input logic       overrun_error,
  input logic       m_axis_tvalid,
  input logic       m_axis_tready,
  input logic [7:0] m_axis_tdata
);

  // 1: frame_error seen while 8'h3C has been held stalled, no handshake since
  reg st;

  always @(posedge clk) begin
    if (rst) begin
      st <= 1'b0;
    end else begin
      if (!m_axis_tvalid || m_axis_tready || m_axis_tdata != 8'h3C) begin
        st <= 1'b0;
      end else if (frame_error) begin
        st <= 1'b1;
      end
    end
  end

  R26_frame_error_then_overrun: cover property (@(posedge clk) disable iff (rst)
    st && overrun_error && m_axis_tvalid && (m_axis_tdata == 8'hA5) &&
    ($past(m_axis_tdata) == 8'h3C) && !$past(m_axis_tready));

endmodule

bind uart_rx cov_R26 u_cov_R26 (.*);
