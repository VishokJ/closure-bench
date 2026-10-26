// Word accepted after exactly one stall cycle following the rise of m_axis_tvalid.
module cov_P10 (
  input logic       clk,
  input logic       rst,
  input logic [7:0] m_axis_tdata,
  input logic       m_axis_tvalid,
  input logic       m_axis_tready
);

  // Number of consecutive stalled cycles since m_axis_tvalid rose
  // (0: not tracking; saturates at 3).
  reg [1:0] cnt;

  always @(posedge clk) begin
    if (rst) begin
      cnt <= 2'd0;
    end else if ($rose(m_axis_tvalid)) begin
      if (m_axis_tready) cnt <= 2'd0;
      else cnt <= 2'd1;
    end else if (m_axis_tvalid && !m_axis_tready) begin
      if (cnt != 2'd0 && cnt != 2'd3) cnt <= cnt + 2'd1;
    end else begin
      cnt <= 2'd0;
    end
  end

  P10_rx_single_cycle_stall_accept: cover property (@(posedge clk) disable iff (rst)
    cnt == 2'd1 && m_axis_tvalid && m_axis_tready && m_axis_tdata == 8'hA5);

endmodule

bind uart_rx cov_P10 u_cov_P10 (.*);
