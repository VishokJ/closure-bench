// Twin: same sequence, but the second word 8'hA5 is accepted after exactly two
// stall cycles instead of one.
module cov_P10_twin (
  input logic       clk,
  input logic       rst,
  input logic [7:0] m_axis_tdata,
  input logic       m_axis_tvalid,
  input logic       m_axis_tready
);

  reg       seen_first;
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

  P10_twin_rx_two_cycle_stall_accept: cover property (@(posedge clk) disable iff (rst)
    seen_first && cnt == 2'd2 && m_axis_tvalid && m_axis_tready && m_axis_tdata == 8'hA5);

endmodule

bind uart_rx cov_P10_twin u_cov_P10_twin (.*);
