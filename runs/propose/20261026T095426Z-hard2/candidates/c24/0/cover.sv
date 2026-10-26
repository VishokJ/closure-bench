// Stop bit length at prescale 1 with back-to-back frames: txd high for
// exactly 9 clocks (stop reload prescale<<3 = 8, plus the idle/load clock).
module cov_P24 (
  input logic        clk,
  input logic        rst,
  input logic        txd,
  input logic [15:0] prescale,
  input logic [3:0]  bit_cnt
);

  reg       active;
  reg [4:0] cnt;
  reg       txd_q;
  reg [3:0] bc_q;

  always @(posedge clk) begin
    if (rst) begin
      active <= 1'b0;
      cnt    <= 5'd0;
      txd_q  <= 1'b1;
      bc_q   <= 4'd0;
    end else begin
      txd_q <= txd;
      bc_q  <= bit_cnt;
      if (txd && !txd_q && bit_cnt == 4'd0 && bc_q == 4'd1 && prescale == 16'd1) begin
        active <= 1'b1;
        cnt    <= 5'd1;
      end else if (active) begin
        if (prescale != 16'd1) begin
          active <= 1'b0;
        end else if (txd) begin
          if (cnt != 5'd31) cnt <= cnt + 5'd1;
        end else begin
          active <= 1'b0;
        end
      end
    end
  end

  P24_stop_9_clocks_prescale1: cover property (@(posedge clk) disable iff (rst)
    active && !txd && prescale == 16'd1 && bit_cnt == 4'd9 && cnt == 5'd9);

endmodule

bind uart_tx cov_P24 u_cov_P24 (.*);
