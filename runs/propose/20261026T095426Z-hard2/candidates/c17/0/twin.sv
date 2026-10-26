// Twin: reset first sampled one clock late, on the clock right after the
// stop-bit sample (rst was low at the stop sample itself).
module cov_P17_twin (
  input logic        clk,
  input logic        rst,
  input logic [18:0] prescale_reg,
  input logic [3:0]  bit_cnt,
  input logic        rxd_reg,
  input logic        m_axis_tvalid,
  input logic [7:0]  m_axis_tdata
);

  reg rst_q;
  reg stop_q;
  reg armed;

  always @(posedge clk) begin
    rst_q <= rst;
    if (!rst && prescale_reg == 19'd0 && bit_cnt == 4'd1 && rxd_reg && !m_axis_tvalid)
      stop_q <= 1'b1;
    else
      stop_q <= 1'b0;
    if (rst) begin
      if (!rst_q) begin
        if (stop_q) armed <= 1'b1;
        else armed <= 1'b0;
      end
    end else begin
      if (m_axis_tvalid && m_axis_tdata != 8'h5A) armed <= 1'b0;
    end
  end

  P17_twin_rx_rst_after_stop_sample: cover property (@(posedge clk)
    !rst && armed && $rose(m_axis_tvalid) && (m_axis_tdata == 8'h5A));

endmodule

bind uart_rx cov_P17_twin u_cov_P17_twin (.*);
