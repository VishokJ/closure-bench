// Every relational operator, unsigned and signed, against signals, parameters and
// constants. Verilator 5.020 lowers them to lt/lte/gt/gte (and the signed lts/ltes/
// gts/gtes), swapping operands when one side folds to a constant (smoke run c01:
// `bit_cnt > DATA_WIDTH+1` became lt). All are pure comparisons.
module cov_X #(parameter int DATA_WIDTH = 8) (
  input logic clk, input logic rst, input logic [3:0] bit_cnt, input logic [7:0] data_reg,
  input logic [18:0] prescale_reg, input logic [15:0] prescale
);
  logic a, b, c, d, e;
  always @(posedge clk) begin
    if (rst) begin
      a <= 0; b <= 0; c <= 0; d <= 0; e <= 0;
    end else begin
      a <= bit_cnt > DATA_WIDTH+1 && bit_cnt < 4'd9 && bit_cnt >= 4'd2 && bit_cnt <= DATA_WIDTH;
      b <= prescale_reg > prescale && prescale_reg < prescale && prescale_reg >= prescale && prescale_reg <= prescale;
      c <= $signed(data_reg) > $signed(prescale[7:0]) && $signed(data_reg) < $signed(prescale[7:0])
           && $signed(data_reg) >= $signed(prescale[7:0]) && $signed(data_reg) <= $signed(prescale[7:0]);
      d <= $signed(data_reg) < 0 && $signed(data_reg) >= -8'sd3;
      e <= 4'd3 < bit_cnt && 4'd3 >= bit_cnt;
    end
  end
  X_a: cover property (@(posedge clk) disable iff (rst) a || b || c || d || e);
endmodule
bind uart_rx cov_X u_cov_X (.*);
