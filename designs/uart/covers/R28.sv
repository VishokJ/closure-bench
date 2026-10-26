// A pending word (8'h3C, sink stalled) survives a rejected (false) start bit,
// is transferred intact at the next handshake with no overrun, and the
// receiver then delivers a fresh word 8'hA5.
module cov_R28 (
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

  // 0: idle; 1: false start seen with 8'h3C pending and stalled;
  // 2: 8'h3C handed off cleanly afterwards
  reg [1:0] st;

  always @(posedge clk) begin
    if (rst) begin
      st <= 2'd0;
    end else begin
      if (st == 2'd0) begin
        if (prescale_reg == 19'd0 && bit_cnt == 4'd10 && rxd_reg &&
            m_axis_tvalid && !m_axis_tready && m_axis_tdata == 8'h3C) begin
          st <= 2'd1;
        end
      end else if (st == 2'd1) begin
        if (overrun_error || !m_axis_tvalid) begin
          st <= 2'd0;
        end else if (m_axis_tready) begin
          if (m_axis_tdata == 8'h3C) st <= 2'd2;
          else st <= 2'd0;
        end
      end else begin
        if (overrun_error) st <= 2'd0;
      end
    end
  end

  R28_pending_word_survives_false_start: cover property (@(posedge clk) disable iff (rst)
    st == 2'd2 && m_axis_tvalid && !$past(m_axis_tvalid) &&
    (m_axis_tdata == 8'hA5) && !overrun_error);

endmodule

bind uart_rx cov_R28 u_cov_R28 (.*);
