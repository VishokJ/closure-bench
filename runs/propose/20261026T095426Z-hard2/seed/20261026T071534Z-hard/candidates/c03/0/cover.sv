// A word is delivered (m_axis_tvalid rises). The next start bit is accepted
// (bit_cnt loads 10) 1 or 2 clocks later. That frame then delivers 8'h5A
// cleanly.
module cov_P3 (
  input logic       clk,
  input logic       rst,
  input logic [3:0] bit_cnt,
  input logic       m_axis_tvalid,
  input logic [7:0] m_axis_tdata,
  input logic       frame_error
);

  reg       tv_q;
  reg       armed;
  reg [2:0] gap;
  reg       second;
  reg [2:0] start_gap;

  always @(posedge clk) begin
    if (rst) begin
      tv_q      <= 1'b0;
      armed     <= 1'b0;
      gap       <= 3'd0;
      second    <= 1'b0;
      start_gap <= 3'd0;
    end else begin
      tv_q <= m_axis_tvalid;
      if (m_axis_tvalid && !tv_q && bit_cnt == 4'd0) begin
        armed  <= 1'b1;
        gap    <= 3'd1;
        second <= 1'b0;
      end else begin
        if (armed) begin
          if (bit_cnt == 4'd10) begin
            armed     <= 1'b0;
            second    <= 1'b1;
            start_gap <= gap;
          end else if (gap != 3'd7) begin
            gap <= gap + 3'd1;
          end else begin
            armed <= 1'b0;
          end
        end
        if (second && (bit_cnt == 4'd0 || frame_error)) begin
          second <= 1'b0;
        end
      end
    end
  end

  P3_short_stop_back_to_back: cover property (@(posedge clk) disable iff (rst)
    second && m_axis_tvalid && !tv_q && (m_axis_tdata == 8'h5A) && !frame_error &&
    (start_gap >= 3'd1) && (start_gap <= 3'd2));

endmodule

bind uart_rx cov_P3 u_cov_P3 (.*);
