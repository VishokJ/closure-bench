// Twin: same sequence, but the start bit at the mid-start sample is genuine
// (rxd_reg low), i.e. the other value of the deciding bit.
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

  reg [1:0] st;

  always @(posedge clk) begin
    if (rst) begin
      st <= 2'd0;
    end else begin
      if (st == 2'd0) begin
        if (prescale_reg == 19'd0 && bit_cnt == 4'd10 && !rxd_reg &&
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

  P18_twin_pending_word_survives_true_start: cover property (@(posedge clk) disable iff (rst)
    st == 2'd2 && m_axis_tvalid && !$past(m_axis_tvalid) &&
    (m_axis_tdata == 8'hA5) && !overrun_error);

endmodule

bind uart_rx cov_P18_twin u_cov_P18_twin (.*);
