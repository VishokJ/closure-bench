// Tracking state, case, parameters and sampled-value functions.
module cov_X #(parameter int P = 2) (
  input logic clk, input logic rst, input logic frame_error, input logic [7:0] data_reg,
  input logic [3:0] bit_cnt
);
  localparam int N = 3;
  logic [1:0] state;
  logic [7:0] saved;
  logic seen;
  always @(posedge clk) begin
    if (rst) begin
      state <= 0;
      seen <= 0;
    end else begin
      case (state)
        2'd0: if (frame_error) state <= 2'd1;
        2'd1: begin
          saved <= {data_reg[3:0], data_reg[7:4]} ^ 8'h55;
          state <= state + 1'b1;
        end
        default: state <= (data_reg[3:0] == 4'hA && saved != 0) ? 2'd0 : state - 1'b1;
      endcase
      if ($rose(frame_error) || (|data_reg && &bit_cnt) || data_reg >= N) seen <= 1'b1;
    end
  end
  X_a: cover property (@(posedge clk) disable iff (rst)
                       seen && state == 2'd2 && $past(data_reg, 2) < P && !$stable(bit_cnt) && !$fell(frame_error));
endmodule
bind uart_rx cov_X u_cov_X (.*);
