// Twin: the same word received at the next prescale value up (16'd2).
module cov_P11_twin (
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

  reg ok;

  always @(posedge clk) begin
    if (rst) begin
      ok <= 1'b0;
    end else begin
      if (prescale_reg == 19'd0 && bit_cnt == 4'd0 && !rxd_reg) begin
        ok <= (prescale == 16'd2);
      end else if (busy && (prescale != 16'd2 || frame_error)) begin
        ok <= 1'b0;
      end
    end
  end

  P11_twin_rx_prescale2_word: cover property (@(posedge clk) disable iff (rst)
    ok && (prescale == 16'd2) && !frame_error &&
    $rose(m_axis_tvalid) && (m_axis_tdata == 8'h96));

endmodule

bind uart_rx cov_P11_twin u_cov_P11_twin (.*);
