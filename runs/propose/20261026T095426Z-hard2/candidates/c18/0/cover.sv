// A pending word (8'h3C, sink stalled) survives a rejected (false) start bit
// and is then transferred intact at the next handshake, with no overrun.
module cov_P18 (
  input logic        clk,
  input logic        rst,
  input logic [18:0] prescale_reg,
  input logic [3:0]  bit_cnt,
  input logic        rxd_reg,
  input logic        m_axis_tvalid,
  input logic        m_axis_tready,
  input logic [7:0]  m_axis_tdata,
  input logic        overrun_error
);

  reg armed;

  always @(posedge clk) begin
    if (rst) begin
      armed <= 1'b0;
    end else begin
      if (prescale_reg == 19'd0 && bit_cnt == 4'd10 && rxd_reg &&
          m_axis_tvalid && !m_axis_tready && m_axis_tdata == 8'h3C) begin
        armed <= 1'b1;
      end else if (armed) begin
        if (overrun_error || !m_axis_tvalid || m_axis_tready) begin
          armed <= 1'b0;
        end
      end
    end
  end

  P18_pending_word_survives_false_start: cover property (@(posedge clk) disable iff (rst)
    armed && m_axis_tvalid && m_axis_tready && !overrun_error && (m_axis_tdata == 8'h3C));

endmodule

bind uart_rx cov_P18 u_cov_P18 (.*);
