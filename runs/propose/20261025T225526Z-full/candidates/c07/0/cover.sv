// Receive at maximum prescale: prescale_reg must hold the full 19-bit reload
// (0xFFFF << 3) - 1 = 19'h7FFF7, then a word 8'hA5 is delivered.
module cov_P7 (
  input logic        clk,
  input logic        rst,
  input logic [15:0] prescale,
  input logic [18:0] prescale_reg,
  input logic        m_axis_tvalid,
  input logic [7:0]  m_axis_tdata
);

  reg seen_full;

  always @(posedge clk) begin
    if (rst) begin
      seen_full <= 1'b0;
    end else begin
      if (prescale_reg == 19'h7FFF7) begin
        seen_full <= 1'b1;
      end
    end
  end

  P7_rx_max_prescale: cover property (@(posedge clk) disable iff (rst)
    seen_full && (prescale == 16'hFFFF) && $rose(m_axis_tvalid) && (m_axis_tdata == 8'hA5));

endmodule

bind uart_rx cov_P7 u_cov_P7 (.*);
