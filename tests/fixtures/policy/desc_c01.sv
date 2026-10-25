// P1: false start rejected at the mid-start-bit sample, followed by a
// correctly received 0xA5 word with no frame error in between.
// bit_cnt == 10 (DATA_WIDTH+2 for the default width) is the only value
// above DATA_WIDTH+1 that bit_cnt can take, so it marks the start-bit check.
module cov_P1 (
  input logic        clk,
  input logic        rst,
  input logic        rxd_reg,
  input logic [3:0]  bit_cnt,
  input logic [18:0] prescale_reg,
  input logic        m_axis_tvalid,
  input logic [7:0]  m_axis_tdata,
  input logic        frame_error
);

  reg armed;

  always @(posedge clk) begin
    if (rst) begin
      armed <= 1'b0;
    end else begin
      if (prescale_reg == 19'd0 && bit_cnt == 4'd10 && rxd_reg) begin
        armed <= 1'b1;
      end else if (frame_error || (m_axis_tvalid && !(m_axis_tdata == 8'hA5))) begin
        armed <= 1'b0;
      end
    end
  end

  P1_false_start_then_rx: cover property (@(posedge clk) disable iff (rst)
    armed && $rose(m_axis_tvalid) && m_axis_tdata == 8'hA5);

endmodule

bind uart_rx cov_P1 u_cov_P1 (.*);
