// Twin: one clock late. s_axis_tvalid is low on the first clock after reset
// release and first high on the second (tready already high there), so the
// load handshakes normally; the bytes still shift out as 8'hA5 then 8'h3C.
module cov_P21_twin (
  input logic        clk,
  input logic        rst,
  input logic        s_axis_tvalid,
  input logic        s_axis_tready,
  input logic        txd,
  input logic [18:0] prescale_reg,
  input logic [3:0]  bit_cnt
);

  reg       rst_q;
  reg [2:0] st;
  reg [7:0] shift;
  reg       done;

  always @(posedge clk) begin
    rst_q <= rst;
    if (rst) begin
      st    <= 3'd0;
      shift <= 8'h00;
      done  <= 1'b0;
    end else begin
      done <= 1'b0;
      case (st)
        3'd0: begin
          if (rst_q && !s_axis_tvalid) begin
            st <= 3'd1;
          end
        end
        3'd1: begin
          if (s_axis_tvalid && s_axis_tready &&
              prescale_reg == 19'd0 && bit_cnt == 4'd0) begin
            st <= 3'd2;
          end else begin
            st <= 3'd0;
          end
        end
        3'd2: begin
          if (!txd && !s_axis_tready && bit_cnt == 4'd9) begin
            st    <= 3'd3;
            shift <= 8'h00;
          end else begin
            st <= 3'd0;
          end
        end
        3'd3: begin
          if (prescale_reg == 19'd0 && bit_cnt != 4'd0 && bit_cnt <= 4'd8) begin
            shift <= {txd, shift[7:1]};
            if (bit_cnt == 4'd1) begin
              st <= 3'd4;
            end
          end
        end
        3'd4: begin
          if (shift != 8'hA5) begin
            st <= 3'd0;
          end else if (prescale_reg == 19'd0 && bit_cnt == 4'd0 && s_axis_tvalid) begin
            st    <= 3'd5;
            shift <= 8'h00;
          end
        end
        3'd5: begin
          if (prescale_reg == 19'd0 && bit_cnt != 4'd0 && bit_cnt <= 4'd8) begin
            shift <= {txd, shift[7:1]};
            if (bit_cnt == 4'd1) begin
              done <= 1'b1;
              st   <= 3'd0;
            end
          end
        end
        default: begin
          st <= 3'd0;
        end
      endcase
    end
  end

  P21_twin_tvalid_second_clock_after_reset: cover property (@(posedge clk)
    !rst && done && shift == 8'h3C);

endmodule

bind uart_tx cov_P21_twin u_cov_P21_twin (.*);
