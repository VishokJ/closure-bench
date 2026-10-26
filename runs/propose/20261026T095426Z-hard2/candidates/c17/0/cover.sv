// Reset first sampled on the exact stop-bit sample clock of a good frame
// (tvalid low); the interrupted word must not appear, and the first word
// delivered after release is 8'h5A from a new frame.
module cov_P17 (
  input logic        clk,
  input logic        rst,
  input logic [18:0] prescale_reg,
  input logic [3:0]  bit_cnt,
  input logic        rxd_reg,
  input logic        m_axis_tvalid,
  input logic [7:0]  m_axis_tdata
);

  reg rst_q;
  reg armed;

  always @(posedge clk) begin
    rst_q <= rst;
    if (rst) begin
      if (!rst_q) begin
        if (prescale_reg == 19'd0 && bit_cnt == 4'd1 && rxd_reg && !m_axis_tvalid)
          armed <= 1'b1;
        else
          armed <= 1'b0;
      end
    end else begin
      if (m_axis_tvalid && m_axis_tdata != 8'h5A) armed <= 1'b0;
    end
  end

  P17_rx_rst_at_stop_sample: cover property (@(posedge clk)
    !rst && armed && $rose(m_axis_tvalid) && (m_axis_tdata == 8'h5A));

endmodule

bind uart_rx cov_P17 u_cov_P17 (.*);
