// Twin: the same two-edge off-sample glitch, but in the stop-bit interval
// (bit_cnt == 1, just outside the 2..9 data-bit range), with no glitch in any
// data-bit interval; the frame still delivers 8'hA5 with no frame error.
module cov_P4_twin (
  input logic        clk,
  input logic        rst,
  input logic [3:0]  bit_cnt,
  input logic [18:0] prescale_reg,
  input logic        rxd_reg,
  input logic        m_axis_tvalid,
  input logic [7:0]  m_axis_tdata,
  input logic        frame_error
);

  reg       rxd_q;
  reg [1:0] cnt_d;
  reg [1:0] cnt_s;
  reg       seen_d;
  reg       seen_s;

  always @(posedge clk) begin
    if (rst) begin
      rxd_q  <= 1'b1;
      cnt_d  <= 2'd0;
      cnt_s  <= 2'd0;
      seen_d <= 1'b0;
      seen_s <= 1'b0;
    end else begin
      rxd_q <= rxd_reg;
      if (prescale_reg == 19'd0) begin
        cnt_d <= 2'd0;
        cnt_s <= 2'd0;
        if (bit_cnt >= 4'd2 && bit_cnt <= 4'd9 && cnt_d == 2'd2 && rxd_reg == rxd_q) begin
          seen_d <= 1'b1;
        end
        if (bit_cnt == 4'd1 && cnt_s == 2'd2 && rxd_reg == rxd_q) begin
          seen_s <= 1'b1;
        end
        if (bit_cnt == 4'd0 && !rxd_reg) begin
          seen_d <= 1'b0;
          seen_s <= 1'b0;
        end
      end else begin
        if (bit_cnt >= 4'd2 && bit_cnt <= 4'd9 && rxd_reg != rxd_q && cnt_d != 2'd3) begin
          cnt_d <= cnt_d + 2'd1;
        end
        if (bit_cnt == 4'd1 && rxd_reg != rxd_q && cnt_s != 2'd3) begin
          cnt_s <= cnt_s + 2'd1;
        end
      end
    end
  end

  P4_twin_rx_glitch_in_stop_interval: cover property (@(posedge clk) disable iff (rst)
    seen_s && !seen_d && $rose(m_axis_tvalid) && (m_axis_tdata == 8'hA5) && !frame_error);

endmodule

bind uart_rx cov_P4_twin u_cov_P4_twin (.*);
