// A word received entirely at the minimum prescale (16'd1, 8-clock bits).
module cov_P11 (
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
        // A start bit is detected on this edge.
        ok <= (prescale == 16'd1);
      end else if (busy && (prescale != 16'd1 || frame_error)) begin
        ok <= 1'b0;
      end
    end
  end

  P11_rx_min_prescale_word: cover property (@(posedge clk) disable iff (rst)
    ok && (prescale == 16'd1) && !frame_error &&
    $rose(m_axis_tvalid) && (m_axis_tdata == 8'h96));

endmodule

bind uart_rx cov_P11 u_cov_P11 (.*);
