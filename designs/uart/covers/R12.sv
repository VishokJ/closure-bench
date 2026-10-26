// The pending word 8'h3C is accepted on the same clock the next frame
// completes; on the next clock the new word 8'hA5 is presented.
module cov_R12 (
  input logic       clk,
  input logic       rst,
  input logic       m_axis_tvalid,
  input logic       m_axis_tready,
  input logic [7:0] m_axis_tdata
);

  reg       q_valid;
  reg       q_ready;
  reg [7:0] q_data;

  always @(posedge clk) begin
    if (rst) begin
      q_valid <= 1'b0;
      q_ready <= 1'b0;
      q_data  <= 8'h00;
    end else begin
      q_valid <= m_axis_tvalid;
      q_ready <= m_axis_tready;
      q_data  <= m_axis_tdata;
    end
  end

  R12_accept_same_cycle_new_word: cover property (@(posedge clk) disable iff (rst)
    q_valid && q_ready && (q_data == 8'h3C) &&
    m_axis_tvalid && (m_axis_tdata == 8'hA5));

endmodule

bind uart_rx cov_R12 u_cov_R12 (.*);
