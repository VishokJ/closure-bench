// Twin: same pending-word handshake, but the start bit at the mid-start
// sample is genuine (rxd_reg low), i.e. the other value of the deciding bit.
module cov_P18_twin (
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
      if (prescale_reg == 19'd0 && bit_cnt == 4'd10 && !rxd_reg &&
          m_axis_tvalid && !m_axis_tready && m_axis_tdata == 8'h3C) begin
        armed <= 1'b1;
      end else if (armed) begin
        if (overrun_error || !m_axis_tvalid || m_axis_tready) begin
          armed <= 1'b0;
        end
      end
    end
  end

  P18_twin_pending_word_survives_true_start: cover property (@(posedge clk) disable iff (rst)
    armed && m_axis_tvalid && m_axis_tready && !overrun_error && (m_axis_tdata == 8'h3C));

endmodule

bind uart_rx cov_P18_twin u_cov_P18_twin (.*);
