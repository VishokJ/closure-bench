// Twin: one step short. The first frame is glitched off-sample and delivers
// 8'hA5, but the second frame (8'h5A) has no completed data-bit glitch.
module cov_P4_twin (
  input logic        clk,
  input logic        rst,
  input logic [3:0]  bit_cnt,
  input logic [18:0] prescale_reg,
  input logic        rxd_reg,
  input logic        m_axis_tvalid,
  input logic [7:0]  m_axis_tdata,
  input logic        frame_error,
  input logic        overrun_error
);

  reg       rxd_q;
  reg       tv_q;
  reg [1:0] cnt;
  reg       seen;
  reg       stage;

  always @(posedge clk) begin
    if (rst) begin
      rxd_q <= 1'b1;
      tv_q  <= 1'b0;
      cnt   <= 2'd0;
      seen  <= 1'b0;
      stage <= 1'b0;
    end else begin
      rxd_q <= rxd_reg;
      tv_q  <= m_axis_tvalid;
      if (prescale_reg == 19'd0) begin
        cnt <= 2'd0;
        if (bit_cnt >= 4'd2 && bit_cnt <= 4'd9 && cnt == 2'd2 && rxd_reg == rxd_q) begin
          seen <= 1'b1;
        end
        if (bit_cnt == 4'd0 && !rxd_reg) begin
          seen <= 1'b0;
        end
      end else if (bit_cnt >= 4'd2 && bit_cnt <= 4'd9 && rxd_reg != rxd_q && cnt != 2'd3) begin
        cnt <= cnt + 2'd1;
      end
      if (frame_error || overrun_error) begin
        stage <= 1'b0;
      end else if (m_axis_tvalid && !tv_q) begin
        if (seen && m_axis_tdata == 8'hA5) begin
          stage <= 1'b1;
        end else begin
          stage <= 1'b0;
        end
      end
    end
  end

  P4_twin_rx_second_frame_clean: cover property (@(posedge clk) disable iff (rst)
    stage && !seen && m_axis_tvalid && !tv_q && (m_axis_tdata == 8'h5A) &&
    !frame_error && !overrun_error);

endmodule

bind uart_rx cov_P4_twin u_cov_P4_twin (.*);
