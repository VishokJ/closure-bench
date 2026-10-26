// Two consecutive words received entirely at the minimum prescale (16'd1):
// 8'h69 delivered and handed off, then 8'h96 delivered, no frame error.
module cov_R21 (
  input logic        clk,
  input logic        rst,
  input logic [15:0] prescale,
  input logic [18:0] prescale_reg,
  input logic [3:0]  bit_cnt,
  input logic        rxd_reg,
  input logic        busy,
  input logic        frame_error,
  input logic        m_axis_tvalid,
  input logic [7:0]  m_axis_tdata
);

  reg ok;          // current frame started and ran at prescale 1, no frame error
  reg first_done;  // a prescale-1 word 8'h69 was delivered

  always @(posedge clk) begin
    if (rst) begin
      ok         <= 1'b0;
      first_done <= 1'b0;
    end else begin
      if (prescale_reg == 19'd0 && bit_cnt == 4'd0 && !rxd_reg) begin
        ok <= (prescale == 16'd1);
      end else if (busy && (prescale != 16'd1 || frame_error)) begin
        ok <= 1'b0;
      end

      if (prescale != 16'd1 || frame_error) begin
        first_done <= 1'b0;
      end else if (m_axis_tvalid && !$past(m_axis_tvalid)) begin
        if (ok && m_axis_tdata == 8'h69) first_done <= 1'b1;
        else first_done <= 1'b0;
      end
    end
  end

  R21_rx_min_prescale_two_words: cover property (@(posedge clk) disable iff (rst)
    first_done && ok && (prescale == 16'd1) && !frame_error &&
    $rose(m_axis_tvalid) && (m_axis_tdata == 8'h96));

endmodule

bind uart_rx cov_R21 u_cov_R21 (.*);
