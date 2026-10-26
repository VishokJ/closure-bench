// Repeated frame errors during a line break: frame_error pulses at least
// twice while rxd stays low at every clock in between, with m_axis_tvalid low.

module cov_R6 (
  input logic clk,
  input logic rst,
  input logic rxd,
  input logic frame_error,
  input logic m_axis_tvalid
);

  // Number of frame_error pulses seen since rxd was last high (saturating).
  reg [1:0] fe_cnt;

  always @(posedge clk) begin
    if (rst) begin
      fe_cnt <= 2'd0;
    end else if (rxd) begin
      fe_cnt <= 2'd0;
    end else if (frame_error && fe_cnt != 2'd3) begin
      fe_cnt <= fe_cnt + 2'd1;
    end
  end

  R6_break_repeated_frame_error: cover property (@(posedge clk) disable iff (rst)
    frame_error && !rxd && (fe_cnt != 2'd0) && !m_axis_tvalid);

endmodule

bind uart_rx cov_R6 u_cov_R6 (.*);
