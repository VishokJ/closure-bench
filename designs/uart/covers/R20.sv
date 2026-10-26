// A first word 8'h3C is accepted; a later word 8'hA5 is accepted after exactly
// one stall cycle following the rise of m_axis_tvalid.
module cov_R20 (
  input logic       clk,
  input logic       rst,
  input logic [7:0] m_axis_tdata,
  input logic       m_axis_tvalid,
  input logic       m_axis_tready
);

  // Set once a word 8'h3C has been handed off.
  reg       seen_first;
  // Consecutive stalled cycles since m_axis_tvalid rose (0: not tracking; saturates at 3).
  reg [1:0] cnt;

  always @(posedge clk) begin
    if (rst) begin
      seen_first <= 1'b0;
      cnt        <= 2'd0;
    end else begin
      if (m_axis_tvalid && m_axis_tready && m_axis_tdata == 8'h3C) begin
        seen_first <= 1'b1;
      end
      if ($rose(m_axis_tvalid)) begin
        if (m_axis_tready) cnt <= 2'd0;
        else cnt <= 2'd1;
      end else if (m_axis_tvalid && !m_axis_tready) begin
        if (cnt != 2'd0 && cnt != 2'd3) cnt <= cnt + 2'd1;
      end else begin
        cnt <= 2'd0;
      end
    end
  end

  R20_rx_single_cycle_stall_accept: cover property (@(posedge clk) disable iff (rst)
    seen_first && cnt == 2'd1 && m_axis_tvalid && m_axis_tready && m_axis_tdata == 8'hA5);

endmodule

bind uart_rx cov_R20 u_cov_R20 (.*);
