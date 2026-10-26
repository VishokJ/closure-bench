// tvalid presented on the very first clock after reset release, while
// s_axis_tready is still low from reset. The byte must be loaded on that edge
// (txd low, tready high, bit_cnt 9 on the next clock) and shift out as 8'hA5.
module cov_P21 (
  input logic        clk,
  input logic        rst,
  input logic        s_axis_tvalid,
  input logic        s_axis_tready,
  input logic        txd,
  input logic [18:0] prescale_reg,
  input logic [3:0]  bit_cnt
);

  reg       rst_q;
  reg [1:0] st;
  reg [7:0] shift;
  reg       done;

  always @(posedge clk) begin
    rst_q <= rst;
    if (rst) begin
      st    <= 2'd0;
      shift <= 8'h00;
      done  <= 1'b0;
    end else begin
      done <= 1'b0;
      case (st)
        2'd0: begin
          if (rst_q && s_axis_tvalid && !s_axis_tready &&
              prescale_reg == 19'd0 && bit_cnt == 4'd0) begin
            st <= 2'd1;
          end
        end
        2'd1: begin
          if (!txd && s_axis_tready && bit_cnt == 4'd9) begin
            st    <= 2'd2;
            shift <= 8'h00;
          end else begin
            st <= 2'd0;
          end
        end
        2'd2: begin
          if (prescale_reg == 19'd0 && bit_cnt != 4'd0 && bit_cnt <= 4'd8) begin
            shift <= {txd, shift[7:1]};
            if (bit_cnt == 4'd1) begin
              done <= 1'b1;
              st   <= 2'd0;
            end
          end
        end
        default: begin
          st <= 2'd0;
        end
      endcase
    end
  end

  P21_tvalid_first_clock_after_reset: cover property (@(posedge clk)
    !rst && done && shift == 8'hA5);

endmodule

bind uart_tx cov_P21 u_cov_P21 (.*);
