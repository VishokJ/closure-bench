// Near miss: the pending word 8'h3C is accepted one clock before the next
// frame completes (tvalid low in between), then 8'hA5 is presented.
module cov_P1_twin (
  input logic       clk,
  input logic       rst,
  input logic       m_axis_tvalid,
  input logic       m_axis_tready,
  input logic [7:0] m_axis_tdata
);

  reg       q_valid;
  reg       q_ready;
  reg [7:0] q_data;
  reg       q2_valid;
  reg       q2_ready;
  reg [7:0] q2_data;

  always @(posedge clk) begin
    if (rst) begin
      q_valid  <= 1'b0;
      q_ready  <= 1'b0;
      q_data   <= 8'h00;
      q2_valid <= 1'b0;
      q2_ready <= 1'b0;
      q2_data  <= 8'h00;
    end else begin
      q_valid  <= m_axis_tvalid;
      q_ready  <= m_axis_tready;
      q_data   <= m_axis_tdata;
      q2_valid <= q_valid;
      q2_ready <= q_ready;
      q2_data  <= q_data;
    end
  end

  P1_twin_accept_one_early: cover property (@(posedge clk) disable iff (rst)
    q2_valid && q2_ready && (q2_data == 8'h3C) && !q_valid &&
    m_axis_tvalid && (m_axis_tdata == 8'hA5));

endmodule

bind uart_rx cov_P1_twin u_cov_P1_twin (.*);
